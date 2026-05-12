"""LangChain chat wrappers for subscription-backed local AI CLIs.

These providers let users who are authenticated in Codex CLI or Claude Code
run TradingAgents without separate OpenAI/Anthropic API keys. They are a
best-effort compatibility layer: calls are executed by spawning the local CLI
for each LangChain invocation, so they are slower than API providers and do not
support native tool-calling. TradingAgents still works because analyst nodes
fall back to plain text when no tool calls are returned, and structured agents
use prompt-constrained JSON parsing.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, ConfigDict, Field

from .base_client import BaseLLMClient
from .validators import validate_model


class SubscriptionCLIError(RuntimeError):
    """Raised when a subscription-backed CLI cannot produce a response."""


def _message_role(message: BaseMessage) -> str:
    role = getattr(message, "type", "message")
    return {
        "human": "user",
        "ai": "assistant",
        "system": "system",
        "tool": "tool",
    }.get(role, role)


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content)


def _input_to_prompt(input_: Any) -> str:
    if isinstance(input_, str):
        return input_
    if hasattr(input_, "to_messages"):
        input_ = input_.to_messages()
    if isinstance(input_, list):
        lines: list[str] = []
        for message in input_:
            if isinstance(message, BaseMessage):
                role = _message_role(message)
                content = _stringify_content(message.content)
                lines.append(f"[{role}]\n{content}")
            else:
                lines.append(str(message))
        return "\n\n".join(lines)
    return str(input_)


def _schema_json(schema: Any) -> str:
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return json.dumps(schema.model_json_schema(), indent=2)
    if isinstance(schema, dict):
        return json.dumps(schema, indent=2)
    if hasattr(schema, "schema"):
        return json.dumps(schema.schema(), indent=2)
    return json.dumps(schema, indent=2, default=str)


def _extract_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    for candidate in _json_candidates(cleaned):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("response did not contain JSON")


def _json_candidates(text: str) -> list[str]:
    """Return balanced JSON-looking objects/arrays from free-form text."""
    candidates: list[str] = []
    pairs = {"{": "}", "[": "]"}
    for start, char in enumerate(text):
        if char not in pairs:
            continue
        stack = [pairs[char]]
        in_string = False
        escaped = False
        for index in range(start + 1, len(text)):
            current = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current in pairs:
                stack.append(pairs[current])
            elif stack and current == stack[-1]:
                stack.pop()
                if not stack:
                    candidates.append(text[start : index + 1])
                    break
    return candidates


class SubscriptionCLIChatModel(BaseChatModel):
    """Chat model that shells out to Codex CLI or Claude Code."""

    provider: str
    model: str
    command: str
    timeout: int = 600
    workdir: Optional[str] = None
    model_config = ConfigDict(extra="allow")

    @property
    def _llm_type(self) -> str:
        return f"subscription-{self.provider}"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "command": self.command,
        }

    def bind_tools(self, tools: Any, **kwargs: Any):
        """Return self because subscription CLIs do not expose LangChain tool calls.

        TradingAgents analyst nodes handle the no-tool-call case by using the
        returned text as that analyst's report. The prompt still lists the tool
        names, but the local CLI is not allowed to execute arbitrary project
        tools on the framework's behalf.
        """
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any):
        schema_text = _schema_json(schema)

        def invoke(input_: Any):
            prompt = _input_to_prompt(input_)
            structured_prompt = (
                f"{prompt}\n\n"
                "Return only valid JSON that conforms to this JSON Schema. "
                "Do not include markdown fences or explanatory prose.\n"
                f"JSON Schema:\n{schema_text}"
            )
            message = self.invoke(structured_prompt)
            parsed = _extract_json(message.content)
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                return schema.model_validate(parsed)
            return parsed

        return RunnableLambda(invoke)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt = _input_to_prompt(messages)
        if stop:
            prompt += "\n\nStop sequences to respect: " + ", ".join(stop)
        content = self._run_cli(prompt)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    def _run_cli(self, prompt: str) -> str:
        if self.provider == "codex-cli":
            return self._run_codex(prompt)
        if self.provider == "claude-code":
            return self._run_claude(prompt)
        raise SubscriptionCLIError(f"Unsupported subscription CLI provider: {self.provider}")

    def _run_codex(self, prompt: str) -> str:
        temp_file = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        temp_file.close()
        try:
            cmd = [
                self.command,
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "--color",
                "never",
            ]
            if self.model and self.model != "default":
                cmd.extend(["-m", self.model])
            cmd.extend(["-o", temp_file.name, "-"])
            self._run_subprocess(cmd, prompt)
            with open(temp_file.name, "r", encoding="utf-8") as output:
                text = output.read().strip()
        finally:
            if os.path.exists(temp_file.name):
                os.remove(temp_file.name)
        if not text:
            raise SubscriptionCLIError("Codex CLI completed but produced no final message")
        return text

    def _run_claude(self, prompt: str) -> str:
        cmd = [
            self.command,
            "--print",
            "--output-format",
            "text",
            "--no-session-persistence",
        ]
        if self.model and self.model != "default":
            cmd.extend(["--model", self.model])
        result = self._run_subprocess(cmd, prompt)
        text = result.stdout.strip()
        if not text:
            raise SubscriptionCLIError("Claude Code completed but produced no output")
        return text

    def _run_subprocess(self, cmd: list[str], prompt: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                cmd,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=True,
                cwd=self.workdir or os.getcwd(),
            )
        except FileNotFoundError as exc:
            raise SubscriptionCLIError(
                f"Could not find {cmd[0]!r}. Install/login to the CLI or set the matching command env var."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SubscriptionCLIError(
                f"{self.provider} timed out after {self.timeout}s"
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            details = stderr or stdout or f"exit code {exc.returncode}"
            raise SubscriptionCLIError(f"{self.provider} failed: {details}") from exc


class SubscriptionCLIClient(BaseLLMClient):
    """Client for subscription-backed local CLIs such as Codex and Claude Code."""

    def __init__(self, model: str, base_url: Optional[str] = None, provider: str = "codex-cli", **kwargs):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        command_env = {
            "codex-cli": "CODEX_CLI_COMMAND",
            "claude-code": "CLAUDE_CODE_COMMAND",
        }.get(self.provider)
        default_command = {
            "codex-cli": "codex",
            "claude-code": "claude",
        }.get(self.provider)
        if not command_env or not default_command:
            raise ValueError(f"Unsupported subscription provider: {self.provider}")

        command = os.environ.get(command_env) or shutil.which(default_command) or default_command
        timeout = int(os.environ.get("TRADINGAGENTS_SUBSCRIPTION_CLI_TIMEOUT", "600"))
        return SubscriptionCLIChatModel(
            provider=self.provider,
            model=self.model,
            command=command,
            timeout=timeout,
            workdir=self.kwargs.get("workdir"),
        )

    def validate_model(self) -> bool:
        return validate_model(self.provider, self.model)
