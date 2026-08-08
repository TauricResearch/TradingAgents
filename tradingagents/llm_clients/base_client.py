import functools
import logging
import os
import warnings
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


# --- Overload / rate-limit retry -------------------------------------------------
#
# The OpenAI SDK's built-in ``max_retries`` only retries idempotent transient
# errors a couple of times with a short backoff. A saturated inference gateway
# (e.g. a local proxy at 127.0.0.1:15721) can return HTTP 529 "Overloaded" for
# many seconds straight — long enough to exhaust the SDK's retries and surface
# "Service was busy" to the user, who then has to manually retry the whole run.
#
# These helpers wrap a ChatOpenAI/ChatAnthropic/... ``_generate`` (sync) or
# ``_agenerate`` (async) call with tenacity exponential backoff that is
# aggressive enough to ride out a multi-minute gateway overload. They only
# retry *transient* errors (429 / 5xx / timeouts / connection drops); auth,
# validation, and not-found errors fail fast so we don't waste a long backoff
# on a problem a retry can't fix.
#
# The OpenAI SDK maps any HTTP >= 500 (including 529) to InternalServerError,
# and 429 to RateLimitError, so matching on those types covers the gateway
# overload case. The status_code fallback also catches generic HTTP errors
# raised by non-OpenAI providers.

_RETRIABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504, 529})


def _max_attempts() -> int:
    raw = os.environ.get("TRADINGAGENTS_LLM_MAX_ATTEMPTS")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            logger.warning("Invalid TRADINGAGENTS_LLM_MAX_ATTEMPTS=%r; using default", raw)
    return 8


def _max_wait() -> float:
    raw = os.environ.get("TRADINGAGENTS_LLM_RETRY_MAX_WAIT")
    if raw:
        try:
            return max(1.0, float(raw))
        except ValueError:
            logger.warning("Invalid TRADINGAGENTS_LLM_RETRY_MAX_WAIT=%r; using default", raw)
    return 60.0


def _is_transient(exc: BaseException) -> bool:
    """True if ``exc`` is a transient overload/rate-limit/timeout worth retrying."""
    # Type-based match for the openai SDK's exception hierarchy. 529 maps to
    # InternalServerError (any >= 500), 429 to RateLimitError.
    name = type(exc).__name__
    if name in {
        "RateLimitError",
        "InternalServerError",
        "APITimeoutError",
        "APIConnectionError",
        "APIError",  # some gateways wrap 529 in a generic APIError
    }:
        return True
    # Anthropic / Google / generic HTTP errors carry a status code attribute.
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status in _RETRIABLE_STATUS_CODES:
        return True
    # httpx transport errors (connection reset / read timeout at the socket).
    return isinstance(exc, (TimeoutError, ConnectionError))


def _retry_log(retry_state) -> None:
    """Log each retry at warning so the user sees the gateway is overloaded,
    not that the run is broken."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    wait = retry_state.next_action.sleep if retry_state.next_action else 0.0
    attempt = retry_state.attempt_number
    logger.warning(
        "LLM call failed (attempt %d/%d): %s: %s — retrying in %.1fs",
        attempt,
        _max_attempts(),
        type(exc).__name__ if exc else "?",
        str(exc)[:200] if exc else "",
        wait,
    )


def retry_overload_sync(func: Callable) -> Callable:
    """Decorate a sync ``_generate``-style method with overload backoff."""
    from tenacity import (
        Retrying,
        retry_if_exception,
        stop_after_attempt,
        wait_exponential_jitter,
    )

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        for attempt in Retrying(
            reraise=True,
            stop=stop_after_attempt(_max_attempts()),
            wait=wait_exponential_jitter(initial=4.0, max=_max_wait()),
            retry=retry_if_exception(_is_transient),
            before_sleep=_retry_log,
        ):
            with attempt:
                return func(self, *args, **kwargs)

    return wrapper


def retry_overload_async(func: Callable) -> Callable:
    """Decorate an async ``_agenerate``-style method with overload backoff."""
    from tenacity import (
        AsyncRetrying,
        retry_if_exception,
        stop_after_attempt,
        wait_exponential_jitter,
    )

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(_max_attempts()),
            wait=wait_exponential_jitter(initial=4.0, max=_max_wait()),
            retry=retry_if_exception(_is_transient),
            before_sleep=_retry_log,
        ):
            with attempt:
                return await func(self, *args, **kwargs)

    return wrapper


def normalize_content(response):
    """Normalize LLM response content to a plain string.

    Multiple providers (OpenAI Responses API, Google Gemini 3) return content
    as a list of typed blocks, e.g. [{'type': 'reasoning', ...}, {'type': 'text', 'text': '...'}].
    Downstream agents expect response.content to be a string. This extracts
    and joins the text blocks, discarding reasoning/metadata blocks.
    """
    content = response.content
    if isinstance(content, list):
        texts = [
            item.get("text", "")
            if isinstance(item, dict) and item.get("type") == "text"
            else item
            if isinstance(item, str)
            else ""
            for item in content
        ]
        response.content = "\n".join(t for t in texts if t)
    return response


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, model: str, base_url: str | None = None, **kwargs):
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    def get_provider_name(self) -> str:
        """Return the provider name used in warning messages."""
        provider = getattr(self, "provider", None)
        if provider:
            return str(provider)
        return self.__class__.__name__.removesuffix("Client").lower()

    def warn_if_unknown_model(self) -> None:
        """Warn when the model is outside the known list for the provider."""
        if self.validate_model():
            return

        warnings.warn(
            (
                f"Model '{self.model}' is not in the known model list for "
                f"provider '{self.get_provider_name()}'. Continuing anyway."
            ),
            RuntimeWarning,
            stacklevel=2,
        )

    @abstractmethod
    def get_llm(self) -> Any:
        """Return the configured LLM instance."""
        pass

    @abstractmethod
    def validate_model(self) -> bool:
        """Validate that the model is supported by this client."""
        pass
