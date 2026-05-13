"""Subprocess-based chat model base.

Some agentic CLIs ship a headless mode that lets you run a single inference
without authenticating an HTTP client — auth comes from the user's OAuth
session that the CLI already holds. Examples:

- Anthropic Claude Code: ``claude -p ...`` (Pro/Max subscription)
- Google Gemini CLI:     ``gemini -p ...`` (Google AI subscription)

This module provides the common machinery for plugging any such CLI into the
project's LangGraph pipeline as a regular langchain ``BaseChatModel``:

- per-call subprocess spawning with isolation flags
- chat-history serialization
- a JSON-envelope tool-calling protocol so langgraph's ToolNode runs the
  project's tools (the subprocess sees no real tools)
- structured output (Pydantic) via ``--json-schema``-style flags
- consistent ``AIMessage`` shape so the rest of the pipeline doesn't notice

Concrete providers subclass :class:`SubprocessChatModel` and implement just
the CLI-specific bits: which binary, what flags, how to parse the response.
See ``claude_code_client.py`` and ``gemini_cli_client.py`` for examples.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from abc import abstractmethod
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Type, Union

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
        parts: List[str] = []
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


class SubprocessChatModel(BaseChatModel):
    """Abstract base for chat models backed by a headless agent CLI subprocess.

    Subclasses implement five hooks:

    - :meth:`_binary_name`        — CLI binary basename (e.g. ``"claude"``)
    - :meth:`_binary_env_var`     — env var that overrides the binary path
    - :meth:`_build_command`      — argv (excluding stdin) for one call
    - :meth:`_parse_response`     — pull text + optional structured object out of stdout
    - :meth:`_llm_type`           — provider identifier used by langchain

    Plus two optional hooks:

    - :meth:`_subprocess_input`   — what goes on stdin (default: rendered user prompt)
    - :meth:`_subprocess_env`     — env var sanitization (default: passthrough)
    """

    model: str
    timeout: int = 300
    binary_path: Optional[str] = None
    append_system_prompt: Optional[str] = None

    # Set by bind_tools / with_structured_output. Internal.
    bound_tools: Optional[List[Dict[str, Any]]] = None
    json_schema: Optional[Dict[str, Any]] = None

    model_config = {"arbitrary_types_allowed": True}

    # --- Subclass hooks -----------------------------------------------------

    @abstractmethod
    def _binary_name(self) -> str:
        """Basename of the CLI binary, e.g. ``"claude"`` or ``"gemini"``."""

    @abstractmethod
    def _binary_env_var(self) -> str:
        """Env var that overrides the binary path (e.g. ``"CLAUDE_CODE_BIN"``)."""

    @abstractmethod
    def _build_command(
        self,
        binary: str,
        system_prompt: str,
        json_schema: Optional[Dict[str, Any]],
    ) -> List[str]:
        """Return the full argv (binary + flags). Stdin is supplied separately."""

    @abstractmethod
    def _parse_response(
        self,
        stdout: str,
        json_schema: Optional[Dict[str, Any]],
    ) -> Tuple[str, Optional[Any]]:
        """Pull (assistant_text, structured_output) from raw CLI stdout.

        ``structured_output`` should be a parsed dict/list when the CLI honored
        the ``--json-schema``-style flag, otherwise None. The base class will
        prefer ``structured_output`` when ``json_schema`` is set.
        """

    def _subprocess_input(self, system_prompt: str, user_prompt: str) -> str:
        """What to send on stdin. Default: just the rendered user prompt.

        Override if your CLI consumes the system prompt via stdin too.
        """
        return user_prompt

    def _subprocess_env(self, parent_env: Dict[str, str]) -> Dict[str, str]:
        """Mutate/return the env dict the subprocess will inherit. Default: no changes."""
        return parent_env

    # --- Common machinery ---------------------------------------------------

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        system_prompt, user_prompt = self._render_messages(messages)
        result_text, structured = self._run_subprocess(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=self.json_schema,
        )

        # Prefer structured_output when --json-schema was passed and the CLI
        # surfaced it. The text field may otherwise be prose-wrapped JSON.
        if self.json_schema is not None and isinstance(structured, (dict, list)):
            ai_msg = AIMessage(content=json.dumps(structured))
            return ChatResult(generations=[ChatGeneration(message=ai_msg)])

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
    ) -> "SubprocessChatModel":
        """Return a copy of this model with tool definitions attached.

        Tool calls come back via a JSON envelope in the system prompt rather
        than a native tool-use API, since the parent app runs tools in
        langgraph's ToolNode (not inside the CLI subprocess).
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
        """Return a Runnable that produces an instance of ``schema``.

        Subclasses with a ``--json-schema``-style flag get schema-constrained
        output for free. Schemas that are not Pydantic ``BaseModel`` raise
        NotImplementedError so ``invoke_structured_or_freetext`` falls back
        to free-text generation.
        """
        if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
            raise NotImplementedError(
                f"{type(self).__name__}.with_structured_output requires a "
                "Pydantic BaseModel schema."
            )

        json_schema = schema.model_json_schema()
        bound = self.model_copy(update={"json_schema": json_schema})

        def _parse(input_: Any) -> BaseModel:
            ai = bound.invoke(input_)
            content = _content_to_str(getattr(ai, "content", ""))
            return schema.model_validate_json(content)

        return RunnableLambda(_parse)

    def _render_messages(self, messages: List[BaseMessage]) -> Tuple[str, str]:
        """Serialize a langgraph chat history into (system_prompt, user_prompt).

        SystemMessages are concatenated into ``system_prompt``. Everything
        else is role-tagged in ``user_prompt`` with ``### user`` / ``### assistant``
        / ``### tool[name]`` markers so the model can follow the conversation.
        """
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

    def _resolve_binary(self) -> str:
        if self.binary_path:
            return self.binary_path
        env_bin = os.environ.get(self._binary_env_var())
        if env_bin:
            return env_bin
        found = shutil.which(self._binary_name())
        if not found:
            raise RuntimeError(
                f"`{self._binary_name()}` CLI not found on PATH. "
                f"Install it or set {self._binary_env_var()}."
            )
        return found

    def _run_subprocess(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]],
    ) -> Tuple[str, Optional[Any]]:
        """Spawn the CLI once, return (assistant_text, structured_output_or_None)."""
        binary = self._resolve_binary()
        cmd = self._build_command(binary, system_prompt, json_schema)
        stdin_text = self._subprocess_input(system_prompt, user_prompt)
        env = self._subprocess_env(os.environ.copy())

        # Run from a stable temp dir so no project-local CLI config files
        # (e.g. a CLAUDE.md or a `.gemini/`) are auto-discovered as cwd context.
        proc = subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self.timeout,
            check=False,
            env=env,
            cwd=tempfile.gettempdir(),
        )

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(
                f"`{self._binary_name()}` failed (rc={proc.returncode}): {err[:1000]}"
            )

        return self._parse_response(proc.stdout, json_schema)

    # --- Tool envelope parsing ---------------------------------------------

    @staticmethod
    def _extract_tool_envelope(text: str) -> Optional[Dict[str, Any]]:
        """Find a ``{"tool_calls": [...]}`` JSON object inside arbitrary text.

        Models often prefix the envelope with a sentence ("Sure, let me...")
        or wrap it in a code fence even when instructed to emit pure JSON.
        Locate the JSON object by brace-matching around the ``"tool_calls"``
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
