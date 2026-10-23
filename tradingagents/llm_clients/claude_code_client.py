"""Claude through a local Claude Code install (``claude -p``), with no API key.

Each call runs ``claude -p`` once with its built-in tools, MCP servers and
settings turned off, so the CLI acts as a plain completion endpoint signed in
with whatever account Claude Code already uses. Tool calls and structured
output both ride on ``--json-schema``: the model answers with a JSON object and
the tools themselves still run in TradingAgents' own graph.
"""

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Any

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
from langchain_core.utils.function_calling import convert_to_openai_tool

from .base_client import BaseLLMClient

_TOOL_REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "tool_calls": {
            "type": "array",
            "description": "Tools to call now. Leave empty when giving the final answer.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "args": {"type": "object"},
                },
                "required": ["name", "args"],
            },
        },
        "content": {
            "type": "string",
            "description": "The final answer, or empty while calling tools.",
        },
    },
    "required": ["tool_calls", "content"],
}


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content)


def _transcript(messages: list[BaseMessage]) -> tuple[str, str]:
    """The system prompt and the rest of the conversation written out as text."""
    system, turns = [], []
    for message in messages:
        if isinstance(message, SystemMessage):
            system.append(_text(message.content))
        elif isinstance(message, ToolMessage):
            turns.append(f"[Tool result: {message.name or 'tool'}]\n{_text(message.content)}")
        elif isinstance(message, AIMessage):
            said = _text(message.content)
            if message.tool_calls:
                calls = json.dumps(
                    [{"name": c["name"], "args": c["args"]} for c in message.tool_calls],
                    default=str,
                )
                said = f"{said}\n[You called tools: {calls}]".strip()
            turns.append(f"[Assistant]\n{said}")
        elif isinstance(message, HumanMessage):
            turns.append(f"[User]\n{_text(message.content)}")
        else:
            turns.append(_text(message.content))
    return "\n\n".join(system), "\n\n".join(turns)


def _log_usage(model: str, reply: dict) -> None:
    """Append the call's cost and tokens to TRADINGAGENTS_CLAUDE_CODE_USAGE_LOG, when set."""
    path = os.environ.get("TRADINGAGENTS_CLAUDE_CODE_USAGE_LOG")
    if not path:
        return
    entry = {"model": model, "cost_usd": reply.get("total_cost_usd"), "usage": reply.get("usage")}
    with open(path, "a", encoding="utf-8") as log:
        log.write(json.dumps(entry) + "\n")


class ChatClaudeCode(BaseChatModel):
    """A chat model that answers through ``claude -p``."""

    model: str = "claude-sonnet-5"
    effort: str | None = None
    timeout: float = 900
    max_retries: int = 2
    claude_bin: str = "claude"
    tools: list[dict] = []

    @property
    def _llm_type(self) -> str:
        return "claude_code"

    def _run(self, system: str, prompt: str, schema: dict | None) -> dict:
        cmd = [
            self.claude_bin, "-p",
            "--model", self.model,
            "--output-format", "json",
            "--tools", "",
            "--strict-mcp-config",
            "--setting-sources", "",
            "--no-session-persistence",
            "--system-prompt", system or "You are a helpful assistant.",
        ]
        if self.effort:
            cmd += ["--effort", self.effort]
        if schema:
            cmd += ["--json-schema", json.dumps(schema)]
        last_error = None
        # An empty working directory keeps any CLAUDE.md out of the prompt.
        with tempfile.TemporaryDirectory(prefix="ta-claude-") as cwd:
            for _ in range(self.max_retries + 1):
                try:
                    done = subprocess.run(
                        cmd, input=prompt, capture_output=True, text=True,
                        timeout=self.timeout, cwd=cwd,
                    )
                    reply = json.loads(done.stdout)
                    _log_usage(self.model, reply)
                    if reply.get("is_error"):
                        raise RuntimeError(reply.get("result") or "claude -p returned an error")
                    return reply
                except (subprocess.TimeoutExpired, json.JSONDecodeError, RuntimeError) as exc:
                    last_error = exc
                    if isinstance(exc, json.JSONDecodeError):
                        last_error = RuntimeError(
                            f"claude -p gave no JSON (exit {done.returncode}): "
                            f"{(done.stderr or done.stdout)[-500:]}"
                        )
        raise last_error

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        system, prompt = _transcript(messages)
        if not self.tools:
            reply = self._run(system, prompt, None)
            message = AIMessage(content=reply.get("result", ""))
            return ChatResult(generations=[ChatGeneration(message=message)])

        system += (
            "\n\nYou can call these tools; each is listed with its JSON parameter schema:\n"
            + json.dumps(self.tools, indent=1)
            + "\n\nTo call tools, put them in tool_calls with their arguments and leave "
            "content empty; their results come back in the next turn. Once you have the "
            "data you need, return an empty tool_calls and your full answer in content. "
            "That content is the only text the reader sees, so write it out completely "
            "and never refer to earlier messages such as 'see above'."
        )
        out = self._run(system, prompt, _TOOL_REPLY_SCHEMA).get("structured_output") or {}
        known = {t["name"] for t in self.tools}
        calls = [
            {"name": c["name"], "args": c.get("args") or {}, "id": f"call_{uuid.uuid4().hex[:12]}"}
            for c in out.get("tool_calls") or []
            if c.get("name") in known
        ]
        message = AIMessage(content="" if calls else out.get("content", ""), tool_calls=calls)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):
        specs = []
        for tool in tools:
            fn = convert_to_openai_tool(tool)["function"]
            specs.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            })
        return self.model_copy(update={"tools": specs})

    def with_structured_output(self, schema, **kwargs):
        json_schema = schema.model_json_schema() if hasattr(schema, "model_json_schema") else schema

        def call(prompt):
            if isinstance(prompt, str):
                messages = [HumanMessage(content=prompt)]
            elif hasattr(prompt, "to_messages"):
                messages = prompt.to_messages()
            else:
                messages = [
                    m if isinstance(m, BaseMessage)
                    else HumanMessage(content=m["content"]) if m.get("role") != "system"
                    else SystemMessage(content=m["content"])
                    for m in prompt
                ]
            system, text = _transcript(messages)
            out = self._run(system, text, json_schema).get("structured_output")
            if out is None:
                return None
            return schema.model_validate(out) if hasattr(schema, "model_validate") else out

        return RunnableLambda(call)


class ClaudeCodeClient(BaseLLMClient):
    """Client for Claude through the local ``claude`` CLI."""

    provider = "claude_code"

    def get_llm(self) -> Any:
        claude_bin = os.environ.get("CLAUDE_CODE_BIN") or shutil.which("claude")
        if not claude_bin:
            raise RuntimeError(
                "The claude_code provider needs the Claude Code CLI on PATH "
                "(or CLAUDE_CODE_BIN set to it)."
            )
        llm_kwargs = {"model": self.model, "claude_bin": claude_bin}
        for key in ("effort", "timeout", "max_retries"):
            if self.kwargs.get(key) is not None:
                llm_kwargs[key] = self.kwargs[key]
        return ChatClaudeCode(**llm_kwargs)

    def validate_model(self) -> bool:
        return True
