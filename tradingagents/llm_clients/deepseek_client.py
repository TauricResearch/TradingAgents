import os
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_DEFAULT_BASE_URL = "https://api.deepseek.com"
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "callbacks",
    "http_client", "http_async_client", "max_tokens", "temperature",
)


class NormalizedChatDeepSeek(ChatOpenAI):
    """ChatOpenAI wrapper with normalized DeepSeek content output."""

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


class DeepSeekClient(BaseLLMClient):
    """Client for DeepSeek chat and reasoning models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)
        self.provider = "deepseek"

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance for DeepSeek."""
        self.warn_if_unknown_model()

        llm_kwargs = {
            "model": self.model,
            "base_url": self.base_url or _DEFAULT_BASE_URL,
        }

        api_key = self.kwargs.get("api_key") or os.environ.get("DEEPSEEK_API_KEY")
        if api_key:
            llm_kwargs["api_key"] = api_key

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs and key != "api_key":
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatDeepSeek(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for DeepSeek."""
        return validate_model("deepseek", self.model)
