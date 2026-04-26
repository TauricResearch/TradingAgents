import logging
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

logger = logging.getLogger(__name__)

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "max_tokens",
    "callbacks", "http_client", "http_async_client",
    "temperature", "reasoning_effort",
)


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output."""

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI-compatible APIs.

    Supports any OpenAI-compatible backend by setting base_url
    (e.g. OpenAI, OpenRouter, vLLM, LiteLLM, local servers).

    Args:
        model: Model name/identifier (e.g. "claude-opus-4-6", "claude-sonnet-4-6")
        base_url: Custom API base URL. Defaults to OpenAI's official endpoint.
        **kwargs: Additional kwargs passed to ChatOpenAI (api_key, temperature, etc.)
    """

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs: dict[str, Any] = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for OpenAI."""
        return validate_model("openai", self.model)
