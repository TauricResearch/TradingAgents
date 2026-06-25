"""Retry-with-backoff for LLM ``invoke`` calls.

Wraps a chat-model ``invoke`` so transient HTTP failures (429 rate
limit, 5xx, connection reset, timeout) retry automatically with
exponential backoff and jitter. This is the second-biggest lever for
staying under OpenRouter free-tier rate limits: the SDK's built-in
``max_retries`` uses a fixed wait, so a single 429 mid-graph can
abort an otherwise fine run. Exponential backoff with a ``Retry-After``
header budget lets the call recover instead of failing the analyst.

Design notes
------------
* Status-code driven, not class-name driven. We prefer the structured
  ``status_code`` / ``headers`` attributes each provider SDK exposes
  on its error types; we fall back to class-name heuristics for the
  few that don't (or for non-SDK wrappers like httpx directly).
* Respects ``Retry-After`` exactly. OpenRouter, Anthropic, OpenAI, and
  Google all send it on 429s. We honor the header when present, then
  add jitter, then cap at ``max_delay_seconds`` so a misbehaving
  upstream can't pin us for 10 minutes.
* Never raises a new exception type. The original exception propagates
  so the caller (and langgraph's graph runner) sees the same
  ``RateLimitError`` it would have without the wrapper.
* Decorator style: ``@with_retry(RetryPolicy(max_retries=5))`` is the
  intent. ``invoke_with_retry`` is the functional form for tests and
  for the one-off wrap path inside ``NormalizedChatOpenAI.invoke``.
* The policy is parameterized, not global. A test that needs
  ``max_retries=0`` builds a fresh ``RetryPolicy``; the production
  default comes from ``default_config.py`` (and is forwarded through
  the client constructor like ``temperature`` already is).
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Status codes that are safe to retry. 408 (request timeout) and 409
# (conflict) are also retryable per the openai SDK defaults, but
# 409 isn't a rate-limit signal and would mask real conflicts — keep
# the set conservative.
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({
    429,  # rate limit / too many requests
    500,  # internal server error
    502,  # bad gateway
    503,  # service unavailable
    504,  # gateway timeout
})


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for ``invoke_with_retry`` and the ``@with_retry`` decorator.

    Attributes:
        max_retries: Total *additional* attempts after the first. A value
            of 0 disables retrying entirely (the default is 5, which
            tolerates a 1-2 minute hiccup without aborting a 16-call
            graph run).
        base_delay_seconds: Initial wait before retrying. Doubles on
            each subsequent attempt up to ``max_delay_seconds``.
        max_delay_seconds: Hard cap on a single backoff sleep. Keeps
            a misbehaving upstream (or a 10-minute ``Retry-After``)
            from pinning the process.
        jitter: Fraction of the computed delay to randomize. ``0.0``
            disables jitter (deterministic — useful for tests);
            ``0.5`` spreads the wait over [delay/2, 1.5*delay].
        sleep: Indirection for the actual sleep. Tests pass a stub to
            skip real time; production uses ``time.sleep``.
        on_retry: Optional ``callable(attempt, delay, exc)`` invoked
            before each backoff sleep. Use for structured logging /
            metrics without coupling this module to a specific sink.
    """

    max_retries: int = 5
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    jitter: float = 0.5
    sleep: Callable[[float], None] = time.sleep
    on_retry: Optional[Callable[[int, float, BaseException], None]] = None


def is_retryable(exc: BaseException) -> bool:
    """Return True if ``exc`` looks like a transient upstream failure.

    Two gates, in order:

    1. Structured attribute gate — preferred when present. Looks at
       ``exc.status_code`` (openai/Anthropic/Google SDKs) and
       ``exc.response.status_code`` (httpx-style) and the
       ``Retry-After`` header. Most accurate, doesn't depend on
       class names.
    2. Class-name gate — fallback for SDKs that don't expose
       ``status_code`` (e.g. raw httpx exceptions, langchain wrappers
       that swallow the original error). The class names match the
       openai SDK hierarchy that the Anthropic and Google SDKs mirror.
    """
    if _status_code(exc) in RETRYABLE_STATUS_CODES:
        return True
    if _is_retryable_by_class(exc):
        return True
    # Defensive fallback: a bare ``Exception("rate limit")`` from a
    # custom gateway or a transport-level error.
    msg = str(exc).lower()
    if "rate limit" in msg or "too many requests" in msg:
        return True
    if "timed out" in msg or "timeout" in msg:
        return True
    return False


def _status_code(exc: BaseException) -> Optional[int]:
    """Best-effort status-code lookup across SDK variants."""
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code
    return None


def _retry_after_seconds(exc: BaseException) -> Optional[float]:
    """Return the ``Retry-After`` header value, in seconds, or None.

    Accepts both numeric (seconds) and HTTP-date forms per RFC 7231.
    For date forms, we return None rather than computing the wall-clock
    delta — the call site should fall back to exponential backoff in
    that case (a malformed header shouldn't pin the process).
    """
    # openai SDK exposes headers on ``exc.response.headers``
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    if headers is None:
        headers = getattr(exc, "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get("retry-after") or headers.get("Retry-After")
    except Exception:  # noqa: BLE001
        return None
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        # HTTP-date form: not handled here, caller falls back to
        # exponential backoff with jitter.
        return None


_RETRYABLE_CLASS_NAMES: frozenset[str] = frozenset({
    "RateLimitError",
    "InternalServerError",
    "APITimeoutError",
    "APIConnectionError",
    "ServiceUnavailableError",  # anthropic
    "Timeout",  # httpx
    "ConnectError",  # httpx
    "RemoteProtocolError",  # httpx — often a transient mid-stream error
})


def _is_retryable_by_class(exc: BaseException) -> bool:
    """Match by class name — fallback when ``status_code`` is absent."""
    cls_name = type(exc).__name__
    if cls_name in _RETRYABLE_CLASS_NAMES:
        return True
    # Walk the MRO so a subclass of RateLimitError still matches.
    for base in type(exc).__mro__:
        if base.__name__ in _RETRYABLE_CLASS_NAMES:
            return True
    return False


def _compute_delay(
    attempt: int,
    policy: RetryPolicy,
    exc: BaseException,
) -> float:
    """Compute the backoff delay for ``attempt`` (0-based) honoring ``Retry-After``."""
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None and retry_after > 0:
        # Server-told us to wait this long. Add a small jitter so a
        # fleet of concurrent workers doesn't all wake at the same
        # instant and trigger the next 429 in lockstep.
        delay = retry_after * (1.0 + policy.jitter * random.random())
    else:
        # Exponential backoff: 1s, 2s, 4s, 8s, 16s by default. The
        # +0.5 in the exponent seeds the first delay at base_delay
        # exactly when attempt=0.
        delay = policy.base_delay_seconds * (2 ** attempt)
        if policy.jitter > 0:
            spread = delay * policy.jitter
            delay = delay - spread + (2 * spread) * random.random()
    return min(delay, policy.max_delay_seconds)


def invoke_with_retry(
    func: Callable[..., T],
    *args: Any,
    policy: Optional[RetryPolicy] = None,
    **kwargs: Any,
) -> T:
    """Call ``func(*args, **kwargs)`` with retry on transient failures.

    On a non-retryable exception, the exception propagates immediately.
    On a retryable exception, sleeps for the computed delay and tries
    again, up to ``policy.max_retries`` extra attempts. On exhaustion,
    the *last* exception is re-raised unchanged.
    """
    effective = policy or RetryPolicy()
    if effective.max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    last_exc: Optional[BaseException] = None
    total_attempts = effective.max_retries + 1
    for attempt in range(total_attempts):
        try:
            return func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 — we re-raise verbatim
            last_exc = exc
            if attempt >= effective.max_retries or not is_retryable(exc):
                raise
            delay = _compute_delay(attempt, effective, exc)
            if effective.on_retry is not None:
                try:
                    effective.on_retry(attempt, delay, exc)
                except Exception:  # noqa: BLE001 — never let logging break retry
                    logger.debug("on_retry callback raised; continuing", exc_info=True)
            logger.info(
                "llm_retry: %s on attempt %d/%d, sleeping %.2fs",
                type(exc).__name__, attempt + 1, total_attempts, delay,
            )
            effective.sleep(delay)
    # Unreachable: the last iteration either returns or raises.
    assert last_exc is not None  # pragma: no cover
    raise last_exc  # pragma: no cover


def with_retry(policy: Optional[RetryPolicy] = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator form of ``invoke_with_retry``.

    Example::

        @with_retry(RetryPolicy(max_retries=5))
        def invoke(self, input, config=None, **kwargs):
            return super().invoke(input, config, **kwargs)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return invoke_with_retry(func, *args, policy=policy, **kwargs)
        wrapper.__wrapped__ = func  # type: ignore[attr-defined]
        wrapper.__name__ = getattr(func, "__name__", "wrapped")
        return wrapper

    return decorator
