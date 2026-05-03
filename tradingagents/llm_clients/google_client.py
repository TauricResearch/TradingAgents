import os
import threading
from typing import Any, Optional

from langchain_google_genai import ChatGoogleGenerativeAI

from .base_client import BaseLLMClient, normalize_content
from .retry import SlidingWindowRateLimiter, llm_retry
from .validators import validate_model

# Per-model RPM caps. Matched by substring (case-insensitive); first match wins.
# List more-specific patterns before less-specific ones to avoid false matches
# (e.g. "gemini-3.1-flash-lite" must appear before "gemini-3-flash").
_MODEL_RPM_TABLE = [
    ("gemini-3.1-flash-lite", 15),
    ("gemini-3-flash",         5),
]
# Fallback for any model not listed above. Override via GOOGLE_RPM env var.
_DEFAULT_GOOGLE_RPM = int(os.environ.get("GOOGLE_RPM", "15"))

# Lazily-created per-model limiters, shared across all client instances.
# Rate limits are per API key so one limiter per model string is correct.
_model_limiters: dict[str, SlidingWindowRateLimiter] = {}
_model_limiters_lock = threading.Lock()


def _get_google_rate_limiter(model: str) -> SlidingWindowRateLimiter:
    with _model_limiters_lock:
        if model not in _model_limiters:
            model_lower = model.lower()
            rpm = _DEFAULT_GOOGLE_RPM
            for pattern, limit in _MODEL_RPM_TABLE:
                if pattern in model_lower:
                    rpm = limit
                    break
            _model_limiters[model] = SlidingWindowRateLimiter(rpm, 60.0)
        return _model_limiters[model]


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with normalized content output and rate limiting.

    Gemini 3 models return content as list of typed blocks.
    This normalizes to string for consistent downstream handling.
    Enforces the per-model per-minute request cap before each call so agents
    never trigger a 429; they wait for the next available slot instead.
    """

    def invoke(self, input, config=None, **kwargs):
        _get_google_rate_limiter(self.model).acquire()
        return normalize_content(llm_retry(super().invoke, input, config, **kwargs))


class GoogleClient(BaseLLMClient):
    """Client for Google Gemini models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatGoogleGenerativeAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in ("timeout", "max_retries", "callbacks", "http_client", "http_async_client"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Unified api_key maps to provider-specific google_api_key
        google_api_key = self.kwargs.get("api_key") or self.kwargs.get("google_api_key")
        if google_api_key:
            llm_kwargs["google_api_key"] = google_api_key

        # Map thinking_level to appropriate API param based on model
        # Gemini 3 Pro: low, high
        # Gemini 3 Flash: minimal, low, medium, high
        # Gemini 2.5: thinking_budget (0=disable, -1=dynamic)
        thinking_level = self.kwargs.get("thinking_level")
        if thinking_level:
            model_lower = self.model.lower()
            if "gemini-3" in model_lower:
                # Gemini 3 Pro doesn't support "minimal", use "low" instead
                if "pro" in model_lower and thinking_level == "minimal":
                    thinking_level = "low"
                llm_kwargs["thinking_level"] = thinking_level
            else:
                # Gemini 2.5: map to thinking_budget
                llm_kwargs["thinking_budget"] = -1 if thinking_level == "high" else 0

        return NormalizedChatGoogleGenerativeAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Google."""
        return validate_model("google", self.model)
