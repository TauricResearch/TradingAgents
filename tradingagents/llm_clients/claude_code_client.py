"""Experimental Claude Code CLI-backed chat model.

This provider lets TradingAgents route LLM calls through a locally installed
``claude`` command. It is intentionally a subprocess adapter, not an Anthropic
API client: Claude Code is a terminal agent, so this adapter constrains it to
``--print`` mode and disables Claude Code tools. TradingAgents tools still run
through LangGraph's normal tool-call path.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import uuid
from typing import Any, Iterable, Optional, Sequence

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from .base_client import BaseLLMClient


def _coerce_timeout(value: Optional[str], default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _clone_model(model: BaseChatModel, **updates: Any) -> BaseChatModel:
    if hasattr(model, "model_copy"):
        return model.model_copy(update=updates)
    return model.copy(update=updates)


def _message_role(message: BaseMessage) -> str:
    msg_type = getattr(message, "type", "")
    if msg_type == "human":
        return "Human"
    if msg_type == "system":
        return "System"
    if msg_type == "ai":
        return "Assistant"
    if msg_type == "tool":
        return "Tool"
    return message.__class__.__name__


def _message_content(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)


def _tool_schema(tool: Any) -> dict[str, Any]:
    return {
        "name": getattr(tool, "name", tool.__class__.__name__),
        "description": getattr(tool, "description", "") or "",
        "args": getattr(tool, "args", {}) or {},
    }


def _extract_json_object(text: str) -> Optional[dict[str, Any]]:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _format_messages_for_local_agent(
    messages: Iterable[BaseMessage],
    bound_tools: Sequence[Any],
    *,
    agent_name: str,
) -> str:
    chunks: list[str] = []
    for message in messages:
        role = _message_role(message)
        content = _message_content(message)
        if isinstance(message, ToolMessage):
            tool_id = getattr(message, "tool_call_id", "")
            chunks.append(f"{role} result ({tool_id}):\n{content}")
            continue
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            chunks.append(
                f"{role}:\n{content}\nTool calls: "
                f"{json.dumps(tool_calls, ensure_ascii=False, default=str)}"
            )
        else:
            chunks.append(f"{role}:\n{content}")

    prompt = "\n\n".join(chunks)
    if not bound_tools:
        return prompt

    tools = [_tool_schema(tool) for tool in bound_tools]
    tool_instruction = (
        f"You are being used as a chat model inside TradingAgents via {agent_name}. "
        "You may request TradingAgents tool calls, but you must not claim "
        "that you already executed a tool yourself.\n"
        "Return exactly one JSON object and no markdown.\n"
        "For a final answer: {\"content\":\"...\"}\n"
        "For tool calls: {\"content\":\"\",\"tool_calls\":["
        "{\"name\":\"tool_name\",\"args\":{...}}]}\n"
        f"Available tools:\n{json.dumps(tools, ensure_ascii=False, default=str)}"
    )
    return f"{tool_instruction}\n\nConversation:\n{prompt}"


def _message_from_tool_json(parsed: dict[str, Any], *, id_prefix: str) -> AIMessage:
    raw_calls = parsed.get("tool_calls") or []
    tool_calls = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            continue
        name = raw_call.get("name")
        if not name:
            continue
        args = raw_call.get("args") if isinstance(raw_call.get("args"), dict) else {}
        tool_calls.append(
            {
                "name": name,
                "args": args,
                "id": raw_call.get("id") or f"{id_prefix}_{uuid.uuid4().hex}",
            }
        )

    return AIMessage(content=str(parsed.get("content") or ""), tool_calls=tool_calls)


class ClaudeCodeChatModel(BaseChatModel):
    """LangChain chat model that shells out to ``claude -p``."""

    model: str = "sonnet"
    command: str = "claude"
    timeout: int = 600
    effort: Optional[str] = None
    extra_args: Sequence[str] = Field(default_factory=tuple)
    bound_tools: Sequence[Any] = Field(default_factory=tuple)

    @property
    def _llm_type(self) -> str:
        return "claude-code"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "command": self.command,
            "timeout": self.timeout,
            "effort": self.effort,
        }

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ClaudeCodeChatModel":
        return _clone_model(self, bound_tools=tuple(tools))

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "claude-code uses free-text fallback; native structured output is not supported"
        )

    def _format_prompt(self, messages: Iterable[BaseMessage]) -> str:
        return _format_messages_for_local_agent(
            messages,
            self.bound_tools,
            agent_name="Claude Code",
        )

    def _run_claude(self, prompt: str) -> str:
        args = shlex.split(self.command) + [
            "-p",
            "--output-format",
            "text",
            "--no-session-persistence",
            "--model",
            self.model,
            "--tools",
            "",
        ]
        if self.effort:
            args.extend(["--effort", self.effort])
        args.extend(self.extra_args)

        completed = subprocess.run(
            args,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode != 0:
            error_msg = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"claude-code command failed with exit code {completed.returncode}: {error_msg}"
            )
        return completed.stdout.strip()

    def _message_from_output(self, output: str) -> AIMessage:
        if not self.bound_tools:
            return AIMessage(content=output)

        parsed = _extract_json_object(output)
        if not parsed:
            return AIMessage(content=output)

        return _message_from_tool_json(parsed, id_prefix="claude_code")

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        output = self._run_claude(self._format_prompt(messages))
        if stop:
            for marker in stop:
                if marker in output:
                    output = output.split(marker, 1)[0]
                    break
        message = self._message_from_output(output)
        return ChatResult(generations=[ChatGeneration(message=message)])


class ClaudeCodeClient(BaseLLMClient):
    """Client for routing TradingAgents calls through Claude Code CLI."""

    def get_llm(self) -> Any:
        command = self.kwargs.get("command") or "claude"
        timeout = self.kwargs.get("timeout") or 600
        extra_args = self.kwargs.get("extra_args")
        if extra_args is None:
            extra_args = tuple(
                shlex.split(os.environ.get("TRADINGAGENTS_CLAUDE_CODE_EXTRA_ARGS", ""))
            )
        return ClaudeCodeChatModel(
            model=self.model,
            command=command,
            timeout=int(timeout),
            effort=self.kwargs.get("effort"),
            extra_args=tuple(extra_args),
        )

    def validate_model(self) -> bool:
        return True
