"""Ollama client for local model hosting.

Ollama provides an OpenAI-compatible API at localhost:11434/v1.
"""

from typing import Any, Optional, List, Dict
import os

from langchain_ollama import ChatOllama
from langchain_core.messages import BaseMessage

from .base_client import BaseLLMClient, normalize_content


class OllamaClient(BaseLLMClient):
    """Client for local Ollama models.

    Uses Ollama's OpenAI-compatible API directly via ChatOllama.
    No API key required - runs locally.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = "http://localhost:11434/v1",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = "ollama"
        # Ollama doesn't require API key - ChatOllama handles it
        # Don't pass api_key or http_async_client to avoid OpenAI client initialization

    def get_llm(self) -> BaseMessage:
        """Return configured ChatOllama instance."""
        self.warn_if_unknown_model()
        
        llm_kwargs = {"model": self.model}
        
        # Only set base_url if explicitly provided (not from config default)
        if self.base_url and self.base_url != "http://localhost:11434/v1":
            llm_kwargs["base_url"] = self.base_url
        
        return ChatOllama(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate that the model is available in Ollama."""
        # For Ollama, any model name is accepted
        # The model availability is checked at runtime by trying to stream a response
        return True


def create_ollama_client(model: str, **kwargs) -> OllamaClient:
    """Factory to create Ollama client."""
    return OllamaClient(model=model, **kwargs)
