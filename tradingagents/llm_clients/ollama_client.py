import os
from typing import Any, Optional

from langchain_ollama import ChatOllama

from .base_client import BaseLLMClient


class OllamaClient(BaseLLMClient):
    """Client for Ollama models using ChatOllama."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def _normalize_base_url(self, url: str) -> str:
        # ChatOllama expects the root URL, not a /v1 suffix.
        if not url:
            return url
        url = url.rstrip("/")
        if url.endswith("/v1"):
            return url[:-3]
        return url

    def get_llm(self) -> Any:
        """Return configured ChatOllama instance."""
        # Env-based defaults (can be overridden by explicit base_url/model)
        ollama_base_url = os.getenv("OLLAMA_BASE_URL")
        if not ollama_base_url:
            # Avoid inheriting the OpenAI default backend_url when provider is ollama.
            if self.base_url and self.base_url != "https://api.openai.com/v1":
                ollama_base_url = self.base_url
            else:
                ollama_base_url = "https://ollama.com"
        ollama_base_url = self._normalize_base_url(ollama_base_url)

        ollama_model = os.getenv("OLLAMA_MODEL")
        if not ollama_model:
            ollama_model = self.model or "gpt-oss:120b"
        if not ollama_model:
            ollama_model = "gpt-oss:120b-cloud"

        ollama_api_key = os.getenv("OLLAMA_API_KEY")

        llm_kwargs = {
            "model": ollama_model,
            "base_url": ollama_base_url,
            "temperature": self.kwargs.get("temperature", 0),
            "stream": False,
        }

        # Important: pass headers via client_kwargs (httpx)
        if ollama_api_key:
            header_value = ollama_api_key
            if not header_value.lower().startswith(("bearer ", "basic ", "token ")):
                header_value = f"Bearer {header_value}"
            llm_kwargs["client_kwargs"] = {
                "headers": {"Authorization": header_value}
            }

        for key in ("timeout", "max_retries", "callbacks"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return ChatOllama(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Ollama (accept any)."""
        return True
