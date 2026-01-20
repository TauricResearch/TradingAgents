from typing import Any, Optional

from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient
from .validators import validate_model


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatAnthropic instance."""
        llm_kwargs = {
            "model": self.model,
            "max_tokens": self.kwargs.get("max_tokens", 4096),
        }

        for key in ("timeout", "max_retries", "api_key"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        if "thinking_config" in self.kwargs:
            llm_kwargs["thinking"] = self.kwargs["thinking_config"]

        return ChatAnthropic(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Anthropic."""
        return validate_model("anthropic", self.model)
