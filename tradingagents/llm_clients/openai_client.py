import time
from typing import Any, Optional

import httpx
import openai
from langchain_openai import ChatOpenAI
from pydantic import PrivateAttr

from tradingagents.default_config import get_env_value

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


def _is_transient_openai_error(exc: Exception) -> bool:
    """Return True for retryable transport-level failures.

    Keep this intentionally narrow: connection loss, timeouts, and other
    transport interruptions should retry; request/model/policy errors should
    still fail immediately.
    """
    if isinstance(
        exc,
        (
            openai.APIConnectionError,
            openai.APITimeoutError,
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.RemoteProtocolError,
        ),
    ):
        return True

    if isinstance(exc, openai.RateLimitError):
        msg = str(exc).lower()
        return any(
            token in msg
            for token in (
                "temporarily rate-limited upstream",
                "retry shortly",
                "temporarily unavailable",
                "rate limit",
                "rate-limited",
                "429",
            )
        )

    if isinstance(exc, openai.APIError):
        msg = str(exc).lower()
        return any(
            token in msg
            for token in (
                "network connection lost",
                "connection reset",
                "connection aborted",
                "timed out",
                "timeout",
                "temporarily unavailable",
            )
        )

    return isinstance(exc, (ConnectionError, TimeoutError))


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output.

    The Responses API returns content as a list of typed blocks
    (reasoning, text, etc.). This normalizes to string for consistent
    downstream handling.

    Also strips temperature/top_p for GPT-5 family models which use
    reasoning natively and reject these params.
    """
    _manual_retry_attempts: int = PrivateAttr(default=2)
    _manual_retry_base_delay_s: float = PrivateAttr(default=1.0)

    def __init__(self, **kwargs):
        if "gpt-5" in kwargs.get("model", "").lower():
            kwargs.pop("temperature", None)
            kwargs.pop("top_p", None)
        manual_retry_attempts = max(int(kwargs.get("max_retries", 2) or 0), 0)
        manual_retry_base_delay_s = float(kwargs.pop("retry_base_delay_s", 1.0))
        super().__init__(**kwargs)
        self._manual_retry_attempts = manual_retry_attempts
        self._manual_retry_base_delay_s = manual_retry_base_delay_s

    def invoke(self, input, config=None, **kwargs):
        attempts = self._manual_retry_attempts + 1
        for attempt in range(1, attempts + 1):
            try:
                return normalize_content(super().invoke(input, config, **kwargs))
            except Exception as exc:
                if attempt >= attempts or not _is_transient_openai_error(exc):
                    raise
                time.sleep(self._manual_retry_base_delay_s * attempt)

# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client",
)

# Provider base URLs and API key env vars
_PROVIDER_CONFIG = {
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": (None, None),  # base_url comes from config
}


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI, Ollama, OpenRouter, and xAI providers.

    For native OpenAI models, uses the Responses API (/v1/responses) which
    supports reasoning_effort with function tools across all model families
    (GPT-4.1, GPT-5). Third-party compatible providers (xAI, OpenRouter,
    Ollama) use standard Chat Completions.
    """

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

        # Provider-specific base URL and auth
        if self.provider == "ollama":
            host = self.base_url or "http://localhost:11434"
            if not host.rstrip("/").endswith("/v1"):
                host = host.rstrip("/") + "/v1"
            llm_kwargs["base_url"] = host
            llm_kwargs["api_key"] = "ollama"
        elif self.provider == "openai":
            api_key = get_env_value("OPENAI_API_KEY")
            if api_key:
                llm_kwargs["api_key"] = api_key
            if self.base_url:
                llm_kwargs["base_url"] = self.base_url
        elif self.provider in _PROVIDER_CONFIG:
            base_url, api_key_env = _PROVIDER_CONFIG[self.provider]
            llm_kwargs["base_url"] = base_url
            if api_key_env:
                api_key = get_env_value(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        # Forward user-provided kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Native OpenAI: use Responses API for consistent behavior across
        # all model families. Third-party providers use Chat Completions.
        if self.provider == "openai":
            llm_kwargs["use_responses_api"] = True

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
