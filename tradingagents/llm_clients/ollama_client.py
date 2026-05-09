"""Ollama client for local model hosting.

Ollama provides an OpenAI-compatible API at localhost:11434/v1.
"""

from typing import Optional

from langchain_ollama import ChatOllama

from .base_client import BaseLLMClient


class OllamaClient(BaseLLMClient):
    """Client for local Ollama models using ChatOllama (no API key required)."""

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = "ollama"

    def get_llm(self) -> ChatOllama:
        self.warn_if_unknown_model()
        llm_kwargs: dict = {"model": self.model}
        if self.base_url:
            llm_kwargs["base_url"] = self.base_url
        return ChatOllama(**llm_kwargs)

    def validate_model(self) -> bool:
        return True
