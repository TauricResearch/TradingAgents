import os
import socket
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient
from .validators import validate_model


class OllamaConnectionError(Exception):
    """Raised when Ollama server is not running or not accessible."""
    pass


def _check_ollama_connection(host: str = "localhost", port: int = 11434, timeout: float = 2.0) -> bool:
    """Check if Ollama server is running and accessible."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except (socket.error, OSError):
        return False


class UnifiedChatOpenAI(ChatOpenAI):
    """ChatOpenAI subclass that strips temperature/top_p for GPT-5 family models.

    GPT-5 family models use reasoning natively. temperature/top_p are only
    accepted when reasoning.effort is 'none'; with any other effort level
    (or for older GPT-5/GPT-5-mini/GPT-5-nano which always reason) the API
    rejects these params. Langchain defaults temperature=0.7, so we must
    strip it to avoid errors.

    Non-GPT-5 models (GPT-4.1, xAI, Ollama, etc.) are unaffected.
    """

    def __init__(self, **kwargs):
        if "gpt-5" in kwargs.get("model", "").lower():
            kwargs.pop("temperature", None)
            kwargs.pop("top_p", None)
        super().__init__(**kwargs)


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI, Ollama, OpenRouter, and xAI providers."""

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance."""
        llm_kwargs = {"model": self.model}

        if self.provider == "xai":
            llm_kwargs["base_url"] = "https://api.x.ai/v1"
            api_key = os.environ.get("XAI_API_KEY")
            if api_key:
                llm_kwargs["api_key"] = api_key
        elif self.provider == "openrouter":
            llm_kwargs["base_url"] = "https://openrouter.ai/api/v1"
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if api_key:
                llm_kwargs["api_key"] = api_key
        elif self.provider == "ollama":
            # Check if Ollama is running before creating client
            if not _check_ollama_connection():
                raise OllamaConnectionError(
                    "Ollama server is not running. Please start it with:\n"
                    "  • macOS/Linux: ollama serve\n"
                    "  • Or install from: https://ollama.ai\n"
                    "  • Default port: 11434"
                )
            llm_kwargs["base_url"] = "http://localhost:11434/v1"
            llm_kwargs["api_key"] = "ollama"  # Ollama doesn't require auth
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in ("timeout", "max_retries", "reasoning_effort", "api_key", "callbacks", "http_client", "http_async_client"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return UnifiedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
