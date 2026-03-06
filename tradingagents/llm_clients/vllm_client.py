import os
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient


class VLLMClient(BaseLLMClient):
    """Client for vllm models. Uses OpenAI-compatible API."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance for vllm."""
        llm_kwargs = {
            "model": self.model,
            "base_url": self.base_url or os.environ.get("VLLM_API_BASE", "http://localhost:8000/v1"),
            "api_key": self.kwargs.get("api_key") or os.environ.get("VLLM_API_KEY") or "vllm",
        }

        # Add supported parameters
        for key in ("temperature", "top_p", "max_tokens", "timeout", "max_retries", "callbacks"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return ChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model name is provided."""
        return bool(self.model and self.model.strip())
