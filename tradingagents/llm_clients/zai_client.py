import os
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient
from .validators import validate_model


class ZAIClient(BaseLLMClient):
    """Client for Z.AI GLM models over the OpenAI-compatible API."""

    DEFAULT_BASE_URL = "https://api.z.ai/api/coding/paas/v4"

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance for Z.AI."""
        llm_kwargs = {
            "model": self.model,
            "base_url": self.base_url or self.DEFAULT_BASE_URL,
        }

        api_key = os.environ.get("ZAI_API_KEY")
        if api_key:
            llm_kwargs["api_key"] = api_key

        for key in (
            "timeout",
            "max_retries",
            "api_key",
            "callbacks",
            "http_client",
            "http_async_client",
            "temperature",
            "top_p",
            "extra_body",
        ):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return ChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Z.AI."""
        return validate_model("zai", self.model)
