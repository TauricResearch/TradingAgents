from typing import Any, Optional

from langchain_google_genai import ChatGoogleGenerativeAI

from .base_client import BaseLLMClient
from .validators import validate_model


class GoogleClient(BaseLLMClient):
    """Client for Google Gemini models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatGoogleGenerativeAI instance."""
        llm_kwargs = {"model": self.model}

        for key in ("timeout", "max_retries", "google_api_key"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        if "thinking_budget" in self.kwargs and self._is_preview_model():
            llm_kwargs["thinking_budget"] = self.kwargs["thinking_budget"]

        return ChatGoogleGenerativeAI(**llm_kwargs)

    def _is_preview_model(self) -> bool:
        """Check if this is a preview model that supports thinking budget."""
        return "preview" in self.model.lower()

    def validate_model(self) -> bool:
        """Validate model for Google."""
        return validate_model("google", self.model)
