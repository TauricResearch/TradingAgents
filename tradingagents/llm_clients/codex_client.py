from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .base_client import BaseLLMClient
from .codex_chat_model import CodexChatModel
from .validators import validate_model


class CodexClient(BaseLLMClient):
    """Client wrapper for the local Codex app-server provider."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        llm = CodexChatModel(
            model=self.model,
            codex_binary=self.kwargs.get("codex_binary"),
            codex_reasoning_effort=self.kwargs.get("codex_reasoning_effort"),
            codex_summary=self.kwargs.get("codex_summary"),
            codex_personality=self.kwargs.get("codex_personality"),
            codex_workspace_dir=self.kwargs.get(
                "codex_workspace_dir",
                str(Path.home() / ".codex" / "tradingagents-workspace"),
            ),
            codex_request_timeout=self.kwargs.get("codex_request_timeout", 120.0),
            codex_max_retries=self.kwargs.get("codex_max_retries", 2),
            codex_cleanup_threads=self.kwargs.get("codex_cleanup_threads", True),
            session_factory=self.kwargs.get("session_factory"),
            preflight_runner=self.kwargs.get("preflight_runner"),
            callbacks=self.kwargs.get("callbacks"),
        )
        llm.preflight()
        return llm

    def validate_model(self) -> bool:
        return validate_model("codex", self.model)
