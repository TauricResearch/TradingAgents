"""Claude Code subscription provider — routes LLM calls through the local
``claude -p`` headless CLI instead of an HTTP API.

Users with a Claude Pro/Max subscription get the full multi-agent pipeline
without paying per-token API charges. Each call spawns a ``claude`` subprocess,
feeds the serialized chat history on stdin, and parses the JSON result.

Isolation strategy: we cannot use ``--bare`` because that mode disables
OAuth/keychain auth (subscription routing). Instead we layer:

- ``--system-prompt`` (replaces the default system prompt → no CLAUDE.md
  auto-discovery, no auto-memory, no dynamic sections)
- ``--setting-sources ""`` (skip user/project/local settings → no hooks,
  output styles, custom permissions)
- ``--disable-slash-commands`` (no skills)
- ``--tools ""`` (no built-in tools — project tools run in langgraph's ToolNode)
- ``--no-session-persistence`` (no session files written per call)
- run from a temp cwd so no project-local CLAUDE.md is discovered

Tool calling and structured output piggy-back on CLI flags:

- ``bind_tools(tools)`` injects a JSON-envelope tool-call protocol into the
  system prompt; we parse the assistant's reply for ``{"tool_calls": [...]}``.
- ``with_structured_output(schema)`` adds ``--json-schema <schema>`` so the CLI
  enforces JSON-shape conformance.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .base_client import BaseLLMClient
from .subprocess_chat_base import SubprocessChatModel
from .validators import validate_model


class ChatClaudeCode(SubprocessChatModel):
    """LangChain BaseChatModel that delegates each call to ``claude -p``."""

    model: str = "sonnet"
    effort: Optional[str] = None
    max_budget_usd: Optional[float] = None
    force_subscription: bool = False

    @property
    def _llm_type(self) -> str:
        return "claude_code"

    def _binary_name(self) -> str:
        return "claude"

    def _binary_env_var(self) -> str:
        return "CLAUDE_CODE_BIN"

    def _build_command(
        self,
        binary: str,
        system_prompt: str,
        json_schema: Optional[Dict[str, Any]],
    ) -> List[str]:
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
        return cmd

    def _subprocess_env(self, parent_env: Dict[str, str]) -> Dict[str, str]:
        if self.force_subscription:
            parent_env.pop("ANTHROPIC_API_KEY", None)
        return parent_env

    def _parse_response(
        self,
        stdout: str,
        json_schema: Optional[Dict[str, Any]],
    ) -> Tuple[str, Optional[Any]]:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"`claude -p` returned non-JSON output: {stdout[:500]}"
            ) from exc

        if payload.get("is_error"):
            err = payload.get("result") or payload.get("error") or ""
            raise RuntimeError(f"`claude -p` returned error: {str(err)[:500]}")

        if "result" not in payload and "structured_output" not in payload:
            raise RuntimeError(
                f"`claude -p` JSON missing 'result'/'structured_output' field: "
                f"{json.dumps(payload)[:500]}"
            )

        text = payload.get("result", "") or ""
        structured = payload.get("structured_output")
        return text, structured


_PASSTHROUGH_KWARGS = (
    "timeout",
    "effort",
    "max_budget_usd",
    "append_system_prompt",
    "force_subscription",
    "binary_path",
)


class ClaudeCodeClient(BaseLLMClient):
    """Client routing through the user's Claude Code subscription via ``claude -p``."""

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
