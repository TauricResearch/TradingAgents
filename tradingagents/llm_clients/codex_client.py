"""Experimental Codex CLI-backed chat model."""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from .base_client import BaseLLMClient
from .claude_code_client import (
    _clone_model,
    _coerce_timeout,
    _extract_json_object,
    _format_messages_for_local_agent,
    _message_from_tool_json,
)


class CodexChatModel(BaseChatModel):
    """LangChain chat model that shells out to ``codex exec``."""

    model: str = "gpt-5.5"
    command: str = "codex"
    timeout: int = 600
    extra_args: Sequence[str] = Field(default_factory=tuple)
    bound_tools: Sequence[Any] = Field(default_factory=tuple)

    @property
    def _llm_type(self) -> str:
        return "codex"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "command": self.command,
            "timeout": self.timeout,
        }

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "CodexChatModel":
        return _clone_model(self, bound_tools=tuple(tools))

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "codex uses free-text fallback; native structured output is not supported"
        )

    def _format_prompt(self, messages: Iterable[BaseMessage]) -> str:
        return _format_messages_for_local_agent(
            messages,
            self.bound_tools,
            agent_name="Codex",
        )

    def _run_codex(self, prompt: str) -> str:
        with tempfile.NamedTemporaryFile(prefix="tradingagents-codex-", delete=False) as tmp:
            output_path = Path(tmp.name)

        args = [
            self.command,
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--ask-for-approval",
            "never",
            "--color",
            "never",
            "--output-last-message",
            str(output_path),
            "--model",
            self.model,
            "-",
        ]
        args.extend(self.extra_args)

        try:
            completed = subprocess.run(
                args,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
            if completed.returncode != 0:
                stderr = completed.stderr.strip()
                raise RuntimeError(
                    f"codex command failed with exit code {completed.returncode}: {stderr}"
                )
            if output_path.exists():
                output = output_path.read_text(encoding="utf-8").strip()
                if output:
                    return output
            return completed.stdout.strip()
        finally:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _message_from_output(self, output: str) -> AIMessage:
        if not self.bound_tools:
            return AIMessage(content=output)

        parsed = _extract_json_object(output)
        if not parsed:
            return AIMessage(content=output)

        return _message_from_tool_json(parsed, id_prefix="codex")

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        output = self._run_codex(self._format_prompt(messages))
        if stop:
            for marker in stop:
                if marker in output:
                    output = output.split(marker, 1)[0]
                    break
        message = self._message_from_output(output)
        return ChatResult(generations=[ChatGeneration(message=message)])


class CodexClient(BaseLLMClient):
    """Client for routing TradingAgents calls through Codex CLI."""

    def get_llm(self) -> Any:
        command = self.kwargs.get("command") or os.environ.get("CODEX_COMMAND", "codex")
        timeout = self.kwargs.get("timeout")
        if timeout is None:
            timeout = _coerce_timeout(os.environ.get("CODEX_TIMEOUT_SECONDS"), 600)
        extra_args = self.kwargs.get("extra_args")
        if extra_args is None:
            extra_args = tuple(shlex.split(os.environ.get("CODEX_EXTRA_ARGS", "")))
        return CodexChatModel(
            model=self.model,
            command=command,
            timeout=int(timeout),
            extra_args=tuple(extra_args),
        )

    def validate_model(self) -> bool:
        return True
