"""Claude Code subscription provider — routes LLM calls through the local
`claude -p` headless CLI instead of an HTTP API.

Users with a Claude Pro/Max subscription get the full multi-agent pipeline
without paying per-token API charges. Each call spawns a `claude` subprocess,
feeds the serialized chat history on stdin, and parses the JSON result.

Isolation strategy: we cannot use `--bare` because that mode disables
OAuth/keychain auth (subscription routing). Instead we layer:
- `--system-prompt` (replaces the default system prompt → no CLAUDE.md
  auto-discovery, no auto-memory, no dynamic sections)
- `--setting-sources ""` (skip user/project/local settings → no hooks,
  output styles, custom permissions)
- `--disable-slash-commands` (no skills)
- `--tools ""` (no built-in tools — project tools run in langgraph's ToolNode)
- `--no-session-persistence` (no session files written per call)
- run from a temp cwd so no project-local CLAUDE.md is discovered

Tool calling and structured output piggy-back on CLI flags:
- `bind_tools(tools)` injects a JSON-envelope tool-call protocol into the
  system prompt; we parse the assistant's reply for `{"tool_calls": [...]}`.
- `with_structured_output(schema)` adds `--json-schema <schema>` so the CLI
  enforces JSON-shape conformance.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence, Type, Union

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel

from .base_client import BaseLLMClient
from .validators import validate_model


_TOOL_PROTOCOL_INSTRUCTION = (
    "TOOL PROTOCOL — READ CAREFULLY.\n"
    "Ignore any tools (MCP, built-in, or otherwise) that you may believe are "
    "available in this environment. The ONLY tools you can call are the ones "
    "listed below, and you call them by emitting a JSON envelope, NOT by "
    "invoking any tool API.\n\n"
    "When you decide to call a tool, your ENTIRE reply must be a single JSON "
    "object — no prose before or after, no markdown, no code fences — matching "
    "this exact shape:\n"
    '{"tool_calls": [{"name": "<tool_name>", "args": {<json_args>}}]}\n'
    "You may include multiple objects in the tool_calls array to fan out. To "
    "respond with normal text instead, write text that does not start with '{'.\n\n"
    "Available tools (JSON-Schema):\n"
)


def _content_to_str(content: Any) -> str:
    """Reduce langchain message content (str | list[block]) to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif "text" in item:
                    parts.append(item["text"])
        return "\n".join(p for p in parts if p)
    if content is None:
        return ""
    return str(content)


class ChatClaudeCode(BaseChatModel):
    """LangChain BaseChatModel that delegates each call to `claude -p`."""

    model: str = "sonnet"
    timeout: int = 300
    effort: Optional[str] = None
    max_budget_usd: Optional[float] = None
    append_system_prompt: Optional[str] = None
    force_subscription: bool = False
    binary_path: Optional[str] = None

    bound_tools: Optional[List[Dict[str, Any]]] = None
    json_schema: Optional[Dict[str, Any]] = None

    model_config = {"arbitrary_types_allowed": True}

    @property
    def _llm_type(self) -> str:
        return "claude_code"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        system_prompt, user_prompt = self._render_messages(messages)
        payload = self._run_subprocess(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=self.json_schema,
        )

        # When --json-schema was passed, the CLI parses the assistant's reply
        # against the schema and surfaces the parsed object on a separate
        # `structured_output` field. The `result` field still holds the
        # assistant's prose, which may wrap the JSON in markdown.
        if self.json_schema is not None and isinstance(
            payload.get("structured_output"), (dict, list)
        ):
            content = json.dumps(payload["structured_output"])
            ai_msg = AIMessage(content=content)
            return ChatResult(generations=[ChatGeneration(message=ai_msg)])

        result_text = payload.get("result", "") or ""

        if self.bound_tools:
            envelope = self._extract_tool_envelope(result_text)
            if envelope is not None:
                tool_calls = self._parse_tool_calls(envelope)
                if tool_calls:
                    ai_msg = AIMessage(content="", tool_calls=tool_calls)
                    return ChatResult(generations=[ChatGeneration(message=ai_msg)])

        ai_msg = AIMessage(content=result_text)
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

    def bind_tools(
        self,
        tools: Sequence[Union[Dict[str, Any], Type[BaseModel], Callable, BaseTool]],
        **kwargs: Any,
    ) -> "ChatClaudeCode":
        """Return a copy of this model with tool definitions attached.

        Tool calls come back via a JSON envelope in the system prompt rather
        than a native tool-use API, since the parent app runs tools in
        langgraph's ToolNode (not inside the `claude` subprocess).
        """
        formatted: List[Dict[str, Any]] = []
        for t in tools:
            spec = convert_to_openai_tool(t)
            fn = spec.get("function", spec)
            formatted.append(
                {
                    "name": fn.get("name"),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {}),
                }
            )
        return self.model_copy(update={"bound_tools": formatted})

    def with_structured_output(
        self,
        schema: Type[BaseModel],
        **kwargs: Any,
    ):
        """Return a Runnable that produces an instance of `schema`.

        Uses `claude -p --json-schema`, which constrains the assistant's reply
        to valid JSON matching the schema. The result is parsed into a Pydantic
        instance. Raises NotImplementedError for non-Pydantic schemas so
        invoke_structured_or_freetext falls back to free-text generation.
        """
        if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
            raise NotImplementedError(
                "ChatClaudeCode.with_structured_output requires a Pydantic "
                "BaseModel schema."
            )

        json_schema = schema.model_json_schema()
        bound = self.model_copy(update={"json_schema": json_schema})

        def _parse(input_: Any) -> BaseModel:
            ai = bound.invoke(input_)
            content = _content_to_str(getattr(ai, "content", ""))
            return schema.model_validate_json(content)

        return RunnableLambda(_parse)

    def _render_messages(
        self, messages: List[BaseMessage]
    ) -> tuple[str, str]:
        sys_parts: List[str] = []
        if self.append_system_prompt:
            sys_parts.append(self.append_system_prompt)

        body_parts: List[str] = []
        for msg in messages:
            text = _content_to_str(getattr(msg, "content", ""))
            if isinstance(msg, SystemMessage):
                if text:
                    sys_parts.append(text)
            elif isinstance(msg, HumanMessage):
                body_parts.append(f"### user\n{text}")
            elif isinstance(msg, AIMessage):
                rendered = text
                tool_calls = getattr(msg, "tool_calls", None) or []
                if tool_calls:
                    envelope = {
                        "tool_calls": [
                            {"name": tc.get("name"), "args": tc.get("args", {})}
                            for tc in tool_calls
                        ]
                    }
                    rendered = (rendered + "\n" if rendered else "") + json.dumps(envelope)
                body_parts.append(f"### assistant\n{rendered}")
            elif isinstance(msg, ToolMessage):
                tool_name = getattr(msg, "name", None) or "tool"
                body_parts.append(f"### tool[{tool_name}]\n{text}")
            else:
                role = getattr(msg, "type", "unknown")
                body_parts.append(f"### {role}\n{text}")

        if self.bound_tools:
            tools_doc = json.dumps(self.bound_tools, indent=2)
            sys_parts.append(_TOOL_PROTOCOL_INSTRUCTION + tools_doc)

        system_prompt = "\n\n".join(p for p in sys_parts if p).strip()
        user_prompt = "\n\n".join(body_parts).strip() or "(no user message)"
        return system_prompt, user_prompt

    def _run_subprocess(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        binary = self.binary_path or os.environ.get("CLAUDE_CODE_BIN") or shutil.which("claude")
        if not binary:
            raise RuntimeError(
                "`claude` CLI not found. Install Claude Code "
                "(https://claude.com/code) or set CLAUDE_CODE_BIN."
            )

        # Always pass --system-prompt to suppress the default (which would
        # auto-discover CLAUDE.md from cwd and inject memory paths). When the
        # caller has no system content, fall back to a minimal placeholder.
        effective_system = system_prompt or "You are a helpful AI assistant."

        cmd: List[str] = [
            binary, "-p",
            "--system-prompt", effective_system,
            "--tools", "",
            "--output-format", "json",
            "--no-session-persistence",
            "--setting-sources", "",
            "--disable-slash-commands",
            "--strict-mcp-config",
            "--model", self.model,
        ]
        if self.effort:
            cmd += ["--effort", self.effort]
        if self.max_budget_usd is not None:
            cmd += ["--max-budget-usd", str(self.max_budget_usd)]
        if json_schema is not None:
            cmd += ["--json-schema", json.dumps(json_schema)]

        env = os.environ.copy()
        if self.force_subscription:
            env.pop("ANTHROPIC_API_KEY", None)

        # Run from a stable temp directory so no project-local CLAUDE.md is
        # auto-discovered as the cwd context. The default system prompt would
        # also pull this in; --system-prompt above already overrides it, but
        # belt-and-suspenders.
        proc = subprocess.run(
            cmd,
            input=user_prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
            env=env,
            cwd=tempfile.gettempdir(),
        )

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(
                f"`claude -p` failed (rc={proc.returncode}): {err[:1000]}"
            )

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"`claude -p` returned non-JSON output: {proc.stdout[:500]}"
            ) from exc

        if payload.get("is_error"):
            err = payload.get("result") or payload.get("error") or ""
            raise RuntimeError(f"`claude -p` returned error: {str(err)[:500]}")

        if "result" not in payload and "structured_output" not in payload:
            raise RuntimeError(
                f"`claude -p` JSON missing 'result'/'structured_output' field: "
                f"{json.dumps(payload)[:500]}"
            )

        return payload

    @staticmethod
    def _extract_tool_envelope(text: str) -> Optional[Dict[str, Any]]:
        """Find a `{"tool_calls": [...]}` JSON object inside arbitrary text.

        Models often prefix the envelope with a sentence ("Sure, let me...")
        or wrap it in a code fence, even when instructed to emit pure JSON.
        Locate the JSON object by brace-matching around the `"tool_calls"`
        substring and try to parse it.
        """
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                obj = json.loads(stripped)
                if isinstance(obj, dict) and isinstance(obj.get("tool_calls"), list):
                    return obj
            except json.JSONDecodeError:
                pass

        needle = '"tool_calls"'
        idx = text.find(needle)
        if idx == -1:
            return None
        start = text.rfind("{", 0, idx)
        if start == -1:
            return None

        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not escape:
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        return None
                    if isinstance(obj, dict) and isinstance(obj.get("tool_calls"), list):
                        return obj
                    return None
        return None

    @staticmethod
    def _parse_tool_calls(envelope: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_calls = envelope.get("tool_calls", [])
        out: List[Dict[str, Any]] = []
        for raw in raw_calls:
            if not isinstance(raw, dict):
                continue
            name = raw.get("name")
            if not name:
                continue
            args = raw.get("args", {})
            if not isinstance(args, dict):
                args = {}
            out.append(
                {
                    "name": name,
                    "args": args,
                    "id": raw.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                    "type": "tool_call",
                }
            )
        return out


_PASSTHROUGH_KWARGS = (
    "timeout",
    "effort",
    "max_budget_usd",
    "append_system_prompt",
    "force_subscription",
    "binary_path",
)


class ClaudeCodeClient(BaseLLMClient):
    """Client routing through the user's Claude Code subscription via `claude -p`."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs: Any):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        llm_kwargs: Dict[str, Any] = {"model": self.model}
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs and self.kwargs[key] is not None:
                llm_kwargs[key] = self.kwargs[key]
        return ChatClaudeCode(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model("claude_code", self.model)
