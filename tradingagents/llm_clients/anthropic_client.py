import logging
import time
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

logger = logging.getLogger(__name__)

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "max_tokens",
    "callbacks", "http_client", "http_async_client", "effort",
)


def _is_minimax_anthropic_base_url(base_url: Optional[str]) -> bool:
    return "api.minimaxi.com/anthropic" in str(base_url or "").lower()


def _is_retryable_minimax_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    retry_markers = (
        "overloaded_error",
        "http_code': '529'",
        'http_code": "529"',
        " 529 ",
        "429",
        "timeout",
        "timed out",
        "connection reset",
        "temporarily unavailable",
    )
    return any(marker in text for marker in retry_markers)


class NormalizedChatAnthropic(ChatAnthropic):
    """ChatAnthropic with normalized content output.

    Claude models with extended thinking or tool use return content as a
    list of typed blocks. This normalizes to string for consistent
    downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        extra_attempts = max(0, int(getattr(self, "_minimax_retry_attempts", 0)))
        base_delay = max(0.0, float(getattr(self, "_minimax_retry_base_delay", 0.0)))

        for attempt in range(extra_attempts + 1):
            try:
                return normalize_content(super().invoke(input, config, **kwargs))
            except Exception as exc:
                if attempt >= extra_attempts or not _is_retryable_minimax_error(exc):
                    raise

                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "MiniMax Anthropic invoke failed (%s); retrying in %.1fs (%s/%s)",
                    exc,
                    delay,
                    attempt + 1,
                    extra_attempts,
                )
                time.sleep(delay)


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatAnthropic instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        llm = NormalizedChatAnthropic(**llm_kwargs)
        if _is_minimax_anthropic_base_url(self.base_url):
            object.__setattr__(
                llm,
                "_minimax_retry_attempts",
                int(self.kwargs.get("minimax_retry_attempts", 0)),
            )
            object.__setattr__(
                llm,
                "_minimax_retry_base_delay",
                float(self.kwargs.get("minimax_retry_base_delay", 0.0)),
            )
        return llm

    def validate_model(self) -> bool:
        """Validate model for Anthropic."""
        return validate_model("anthropic", self.model)
