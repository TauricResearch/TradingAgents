"""LLM client for the Claude CLI (``claude -p``) provider.

Follows the same ``BaseLLMClient`` contract as ``anthropic_client.py``
and ``openai_client.py``.  The key difference: no API key is required.
Auth is handled by the user's existing ``claude auth login`` session
(Claude Max subscription).

See also: PLAN.md Phase 1, Task 1.2.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .base_client import BaseLLMClient
from .claude_cli_chat import ClaudeCLIChat, _find_claude_binary

logger = logging.getLogger(__name__)


class ClaudeCLIClient(BaseLLMClient):
    """Client for Claude CLI (``claude -p``) provider.

    Both ``deep_think_llm`` and ``quick_think_llm`` route through the
    same CLI binary — model selection is handled by the ``--model`` flag
    (or the user's default session model when ``model`` is ``None``).
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return a configured :class:`ClaudeCLIChat` instance.

        Validates that the ``claude`` binary exists on PATH before
        constructing the model. Raises ``FileNotFoundError`` if missing.
        """
        self._validate_cli_available()

        llm_kwargs: dict[str, Any] = {}

        # model_name=None means "use whatever the CLI session default is"
        if self.model and self.model != "default":
            llm_kwargs["model_name"] = self.model

        # Forward optional config overrides
        if "timeout" in self.kwargs:
            llm_kwargs["timeout"] = int(self.kwargs["timeout"])
        if "max_retries" in self.kwargs:
            llm_kwargs["max_retries"] = int(self.kwargs["max_retries"])

        return ClaudeCLIChat(**llm_kwargs)

    def validate_model(self) -> bool:
        """Any model string is accepted — the CLI validates server-side."""
        if self.model and self.model != "default":
            logger.debug("Claude CLI will use model=%s (validated server-side)", self.model)
        return True

    @staticmethod
    def _validate_cli_available() -> None:
        """Raise early if ``claude`` is not on PATH."""
        _find_claude_binary()  # raises FileNotFoundError with clear message
