"""One backoff for every model provider.

Every agent calls the model through its chat client's ``invoke``. OpenAI,
Gemini, Anthropic, Azure, Bedrock, and the OpenAI-compatible servers
(DeepSeek, MiniMax, Ollama, vLLM, OpenRouter, xAI) all use that method, so
a temporary outage is retried here for all of them.

The schedule is exponential backoff with equal jitter: each wait is at
least half of 20s, 40s, 80s, capped at 120s, and the other half is random
so parallel agents do not retry in lockstep. A ``Retry-After`` header, or a
delay in the error body, replaces that wait and is still capped at 120s.
Four attempts total. A 400 or any other permanent error fails immediately.

The provider SDK's own short retry is turned off unless ``llm_max_retries``
is set. Leaving both on makes Gemini fire six fast retries inside each of
these waits, which is what a "high demand" 503 asks us not to do.
"""

from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Callable, Iterator
from typing import TypeVar

from .base_client import normalize_content

logger = logging.getLogger(__name__)

T = TypeVar("T")

_ATTEMPTS = 4
_INITIAL_DELAY = 20.0
_BACKOFF = 2.0
_MAX_DELAY = 120.0

# 408/429/5xx are the provider "try again" statuses. 529 is Anthropic's
# overloaded status, the same kind of spike as Gemini's 503.
_TRANSIENT_CODES = frozenset({408, 429, 500, 502, 503, 504, 529})

# Transport and overload errors that often carry no HTTP status. Matched by
# class name so this module does not import every provider SDK.
_TRANSIENT_NAMES = frozenset({
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "WriteTimeout",
    "PoolTimeout",
    "RemoteProtocolError",
    "APIConnectionError",
    "APITimeoutError",
    "Timeout",
    "InternalServerError",
    "OverloadedError",
    "ServiceUnavailableError",
    "RateLimitError",
    "DeadlineExceededError",
})

# Bedrock reports throttling as a botocore error code, sometimes without an
# HTTP status we can read off the exception.
_AWS_RETRYABLE = frozenset({
    "ThrottlingException",
    "TooManyRequestsException",
    "ServiceUnavailable",
    "ServiceUnavailableException",
    "ModelTimeoutException",
    "ModelNotReadyException",
    "InternalServerException",
    "RequestTimeout",
    "ProvisionedThroughputExceededException",
})

_DELAY_IN_TEXT = (
    re.compile(r"retry in\s+(\d+(?:\.\d+)?)s", re.I),
    re.compile(r"retry[_ ]delay\D{0,40}?(\d+(?:\.\d+)?)", re.I),
)


def _chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        nxt = current.__cause__
        if nxt is None and not current.__suppress_context__:
            nxt = current.__context__
        current = nxt


def _http_status(response) -> int | None:
    status = getattr(response, "status_code", None)
    if type(status) is int:
        return status
    if isinstance(response, dict):
        meta = response.get("ResponseMetadata") or {}
        status = meta.get("HTTPStatusCode")
        if type(status) is int:
            return status
    return None


def _status_code(exc: BaseException) -> int | None:
    value = getattr(exc, "status_code", None)
    if type(value) is int:
        return value
    # ``code`` is the HTTP status for Gemini. OpenAI uses the same attribute
    # for a string such as "rate_limit_exceeded", which is not a status.
    value = getattr(exc, "code", None)
    if type(value) is int:
        return value
    return _http_status(getattr(exc, "response", None))


def _aws_error_code(exc: BaseException) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    code = (response.get("Error") or {}).get("Code")
    return code if isinstance(code, str) else None


def _is_transient(exc: BaseException) -> bool:
    if _status_code(exc) in _TRANSIENT_CODES:
        return True
    if _aws_error_code(exc) in _AWS_RETRYABLE:
        return True
    # LangChain marks 429, 5xx, timeouts and connection losses this way
    # (ModelRateLimitError, ModelAPIError, and the GoogleAPIError wrapper).
    if getattr(exc, "is_retryable", False) is True:
        return True
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return type(exc).__name__ in _TRANSIENT_NAMES


def is_transient_llm_error(exc: Exception) -> bool:
    """True when another attempt at the same model call may succeed."""
    return any(_is_transient(item) for item in _chain(exc))


def _parse_delay(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            for pattern in _DELAY_IN_TEXT:
                match = pattern.search(value)
                if match:
                    return float(match.group(1))
            return None
    if isinstance(value, dict):
        if "seconds" in value:
            seconds = _parse_delay(value.get("seconds")) or 0.0
            nanos = value.get("nanos") or 0
            try:
                return seconds + float(nanos) / 1_000_000_000
            except (TypeError, ValueError):
                return seconds
        for key in ("retryDelay", "retry_delay", "retry-after"):
            if key in value:
                return _parse_delay(value[key])
    return None


def _header(response, name: str) -> str | None:
    headers = getattr(response, "headers", None)
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    value = getter(name)
    if value is None:
        value = getter(name.title())
    return value if isinstance(value, str) else None


def _server_delay(exc: BaseException) -> float | None:
    for item in _chain(exc):
        response = getattr(item, "response", None)
        delay = _parse_delay(_header(response, "retry-after"))
        if delay is not None:
            return delay
        for attr in ("details", "body"):
            delay = _parse_delay(getattr(item, attr, None))
            if delay is not None:
                return delay
        delay = _parse_delay(str(item))
        if delay is not None:
            return delay
    return None


def _wait_seconds(exc: BaseException, failed_attempts: int) -> float:
    """Equal-jitter wait after ``failed_attempts`` failures (1 on the first).

    Half of the backoff is guaranteed, so a 503 is not retried immediately.
    The other half is random. A server delay replaces the backoff and is
    capped at ``_MAX_DELAY``.
    """
    server = _server_delay(exc)
    if server is not None:
        base = min(_MAX_DELAY, max(server, 0.0))
    else:
        grown = _INITIAL_DELAY * (_BACKOFF ** (failed_attempts - 1))
        base = min(_MAX_DELAY, grown)
    return base * 0.5 + random.uniform(0, base * 0.5)


def call_with_retry(fn: Callable[[], T]) -> T:
    """Run ``fn`` again after a transient provider failure."""
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt == _ATTEMPTS or not is_transient_llm_error(exc):
                raise
            wait = _wait_seconds(exc, attempt)
            logger.warning(
                "Model temporarily unavailable (%s); retrying in %.0fs (attempt %s/%s): %s",
                type(exc).__name__, wait, attempt, _ATTEMPTS, exc,
            )
            time.sleep(wait)
    raise AssertionError("retry loop exited without returning or raising")


def invoke_with_retry(parent_invoke: Callable, input, config, kwargs) -> T:
    """Call the provider ``invoke``, normalizing content and retrying outages.

    ``parent_invoke`` is ``super().invoke`` from the chat-model subclass, so
    the provider class stays the real base and ``super()`` inside the SDK
    still resolves to the SDK.
    """
    return call_with_retry(lambda: normalize_content(parent_invoke(input, config, **kwargs)))


def sdk_max_retries(configured: int | None, *, google: bool = False) -> int:
    """How many retries to leave to the provider SDK.

    ``None`` disables the SDK retry so this module's backoff is the schedule.
    Gemini reads 0 as "use the default" (several fast retries), so the
    disabled value there is 1: the original request, and no SDK retry.
    """
    if configured is None or (google and configured == 0):
        return 1 if google else 0
    return configured
