import os
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient
from .validators import validate_model


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    _DEFAULT_API_URL = "https://api.anthropic.com"

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatAnthropic instance."""
        llm_kwargs = {"model": self.model}

        env_base_url = os.getenv("ANTHROPIC_BASE_URL")
        if self.base_url and (
            not env_base_url or self.base_url.rstrip("/") != self._DEFAULT_API_URL
        ):
            llm_kwargs["anthropic_api_url"] = self.base_url

        for key in ("timeout", "max_retries", "api_key", "max_tokens", "callbacks", "http_client", "http_async_client"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return ChatAnthropic(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Anthropic."""
        return validate_model("anthropic", self.model)
