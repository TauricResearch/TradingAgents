import asyncio
import os
import time
import warnings
from typing import Any, Optional

from langchain_google_genai import ChatGoogleGenerativeAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with normalized content output.

    Gemini 3 models return content as list of typed blocks.
    This normalizes to string for consistent downstream handling.
    """

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        msg = str(exc).lower()
        return (
            "429" in msg
            or "resource_exhausted" in msg
            or "rate limit" in msg
            or "too many requests" in msg
        )

    @staticmethod
    def _rate_limit_delay_seconds() -> int:
        raw = os.getenv("GOOGLE_429_RETRY_DELAY_SECONDS", "60").strip()
        try:
            value = int(raw)
        except ValueError:
            return 60
        return value if value > 0 else 60

    def _invoke_with_rate_limit_retry(self, call):
        try:
            return call()
        except Exception as exc:
            if not self._is_rate_limited(exc):
                raise
            delay = self._rate_limit_delay_seconds()
            warnings.warn(
                (
                    f"Google API rate limit encountered (429). "
                    f"Retrying once after {delay} seconds."
                ),
                RuntimeWarning,
                stacklevel=2,
            )
            time.sleep(delay)
            return call()

    async def _ainvoke_with_rate_limit_retry(self, call):
        try:
            return await call()
        except Exception as exc:
            if not self._is_rate_limited(exc):
                raise
            delay = self._rate_limit_delay_seconds()
            warnings.warn(
                (
                    f"Google API rate limit encountered (429). "
                    f"Retrying once after {delay} seconds."
                ),
                RuntimeWarning,
                stacklevel=2,
            )
            await asyncio.sleep(delay)
            return await call()

    def invoke(self, input, config=None, **kwargs):
        parent_invoke = super().invoke
        response = self._invoke_with_rate_limit_retry(
            lambda: parent_invoke(input, config, **kwargs)
        )
        return normalize_content(response)

    def _generate(self, *args, **kwargs):
        parent_generate = super()._generate
        return self._invoke_with_rate_limit_retry(
            lambda: parent_generate(*args, **kwargs)
        )

    async def _agenerate(self, *args, **kwargs):
        parent_agenerate = super()._agenerate
        return await self._ainvoke_with_rate_limit_retry(
            lambda: parent_agenerate(*args, **kwargs)
        )


class GoogleClient(BaseLLMClient):
    """Client for Google Gemini models."""

    _MODEL_ALIASES = {
        # Removed or short-lived preview IDs: route to stable 2.5 equivalents.
        "gemini-3.1-flash-lite-preview": "gemini-2.5-flash-lite",
        "gemini-3.1-pro-preview": "gemini-2.5-pro",
        "gemini-3-flash-preview": "gemini-2.5-flash",
    }

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatGoogleGenerativeAI instance."""
        self.warn_if_unknown_model()
        requested_model = self.model
        model = self._MODEL_ALIASES.get(requested_model, requested_model)
        if model != requested_model:
            warnings.warn(
                (
                    f"Google model '{requested_model}' is deprecated or unavailable; "
                    f"using fallback '{model}'."
                ),
                UserWarning,
                stacklevel=2,
            )

        llm_kwargs = {"model": model}

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
            model_lower = model.lower()
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
