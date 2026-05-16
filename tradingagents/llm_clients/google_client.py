import asyncio
import logging
import os
import random
import re
import time
from typing import Any, Callable, Optional, TypeVar

from langchain_google_genai import ChatGoogleGenerativeAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


logger = logging.getLogger(__name__)
T = TypeVar("T")


def _is_resource_exhausted_error(exc: Exception) -> bool:
    """Return True for Gemini quota/rate-limit errors surfaced by Google SDKs."""
    status = getattr(exc, "status", None)
    code = getattr(exc, "code", None)
    details = getattr(exc, "details", None)
    text = " ".join(str(part) for part in (status, code, details, exc) if part is not None)
    upper_text = text.upper()
    return "RESOURCE_EXHAUSTED" in upper_text or " 429 " in f" {upper_text} " or "CODE: 429" in upper_text


def _extract_retry_delay_seconds(exc: Exception) -> Optional[float]:
    """Extract Google's suggested retry delay from SDK exception text, if present."""
    text = str(exc)
    patterns = (
        r"retry(?:\s+in|Delay['\"]?\s*:\s*['\"]?)(\d+(?:\.\d+)?)s",
        r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _quota_retry_count() -> int:
    raw = os.getenv("TRADINGAGENTS_GOOGLE_QUOTA_MAX_RETRIES", "6")
    try:
        return max(0, int(raw))
    except ValueError:
        return 6


def _quota_retry_delay(exc: Exception, attempt: int) -> float:
    configured_cap = os.getenv("TRADINGAGENTS_GOOGLE_QUOTA_RETRY_MAX_DELAY_SECONDS", "90")
    try:
        cap = max(1.0, float(configured_cap))
    except ValueError:
        cap = 90.0

    suggested = _extract_retry_delay_seconds(exc)
    if suggested is not None:
        base_delay = suggested * (attempt + 1)
    else:
        base_delay = 2 ** attempt
    return min(cap, base_delay) + random.uniform(0, 0.5)


def _invoke_with_quota_retry(operation: Callable[[], T]) -> T:
    max_retries = _quota_retry_count()
    for attempt in range(max_retries + 1):
        try:
            return operation()
        except Exception as exc:
            if not _is_resource_exhausted_error(exc) or attempt >= max_retries:
                raise

            delay = _quota_retry_delay(exc, attempt)
            logger.warning(
                "Gemini quota exhausted, retrying in %.1fs (attempt %d/%d)",
                delay,
                attempt + 1,
                max_retries,
            )
            time.sleep(delay)

    raise RuntimeError("unreachable")


async def _ainvoke_with_quota_retry(operation: Callable[[], T]) -> T:
    max_retries = _quota_retry_count()
    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except Exception as exc:
            if not _is_resource_exhausted_error(exc) or attempt >= max_retries:
                raise

            delay = _quota_retry_delay(exc, attempt)
            logger.warning(
                "Gemini quota exhausted, retrying in %.1fs (attempt %d/%d)",
                delay,
                attempt + 1,
                max_retries,
            )
            await asyncio.sleep(delay)

    raise RuntimeError("unreachable")


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with normalized content output.

    Gemini 3 models return content as list of typed blocks.
    This normalizes to string for consistent downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        invoke = super().invoke
        return normalize_content(_invoke_with_quota_retry(lambda: invoke(input, config, **kwargs)))

    async def ainvoke(self, input, config=None, **kwargs):
        ainvoke = super().ainvoke
        return normalize_content(await _ainvoke_with_quota_retry(lambda: ainvoke(input, config, **kwargs)))


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
