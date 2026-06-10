"""Long-horizon retry for provider rate limits (HTTP 429 / 529).

The provider SDKs already retry rate-limited requests in-process
(``llm_max_retries``, default 5) — but with a seconds-scale exponential
backoff that gives up after roughly a minute. That is enough for a burst
limit, yet useless against a drained per-minute token bucket or a busy
subscription window: every quick retry fails, the SDK raises, and a deep
multi-agent run dies half-way, losing every report produced so far.

``call_with_rate_limit_retry`` adds a second, minutes-scale layer on top of
the SDK retries. Each wait honors the server's ``retry-after`` header when
present, otherwise an exponential schedule (20s, 40s, ... capped at 5 min by
default), so a long run rides out the limit instead of crashing.

Two error families are deliberately *not* retried:

* OpenAI's ``insufficient_quota`` 429 — the account is out of credits.
  That is a billing problem; no amount of waiting fixes it.
* Anything that is not a 429/529 — timeouts, connection errors, and 5xx
  are already covered by the SDK retries, and genuine request errors
  (400s) must surface immediately.

Env overrides (read at call time so batch scripts can export them without
code changes; set retries to 0 to disable the layer entirely):

* ``TRADINGAGENTS_RATE_LIMIT_RETRIES``   — extra attempts (default 5)
* ``TRADINGAGENTS_RATE_LIMIT_BASE_WAIT`` — first wait, seconds (default 20)
* ``TRADINGAGENTS_RATE_LIMIT_MAX_WAIT``  — cap per wait, seconds (default 300)
"""

from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 429 = rate limited (every provider); 529 = Anthropic "overloaded_error",
# which Anthropic documents as retry-with-backoff just like a 429.
_RATE_LIMIT_STATUS_CODES = frozenset({429, 529})

_QUOTA_MARKER = "insufficient_quota"

_DEFAULT_RETRIES = 5
_DEFAULT_BASE_WAIT = 20.0
_DEFAULT_MAX_WAIT = 300.0


def _env_number(name: str, default: float, cast) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return cast(raw)
    except ValueError:
        logger.warning("%s=%r is not a number; using default %s", name, raw, default)
        return default


def _status_code(exc: BaseException) -> Optional[int]:
    """HTTP status of an SDK error, from the exception or its response."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def is_rate_limit_error(exc: BaseException) -> bool:
    """True for any provider rate-limit/overloaded error (429 or 529)."""
    return _status_code(exc) in _RATE_LIMIT_STATUS_CODES


def is_quota_exhausted(exc: BaseException) -> bool:
    """True for OpenAI's permanent out-of-credits 429 (``insufficient_quota``).

    The openai SDK exposes the error code as ``exc.code``; older versions and
    proxies only carry it in the JSON body or message, so all three are
    checked.
    """
    if getattr(exc, "code", None) == _QUOTA_MARKER:
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict) and _QUOTA_MARKER in (
            error.get("code"), error.get("type"),
        ):
            return True
    return _QUOTA_MARKER in str(exc)


def is_retryable_rate_limit(exc: BaseException) -> bool:
    """True when waiting and retrying has a chance of succeeding."""
    return is_rate_limit_error(exc) and not is_quota_exhausted(exc)


def _retry_after_seconds(exc: BaseException) -> Optional[float]:
    """Server-suggested wait from the ``retry-after`` header, if any.

    Both the delta-seconds and the HTTP-date form are accepted. httpx
    headers are case-insensitive, so the lowercase lookup matches however
    the server spelled it.
    """
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None:
        return None
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        when = parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return None
    return (when - datetime.now(timezone.utc)).total_seconds()


def call_with_rate_limit_retry(fn: Callable[[], T], *, description: str = "LLM call") -> T:
    """Call ``fn``, sleeping through retryable rate limits before retrying.

    ``description`` names the caller (e.g. the model) in the wait warnings so
    a stalled run is distinguishable from a hung one in the logs.
    """
    max_retries = int(_env_number("TRADINGAGENTS_RATE_LIMIT_RETRIES", _DEFAULT_RETRIES, int))
    base_wait = _env_number("TRADINGAGENTS_RATE_LIMIT_BASE_WAIT", _DEFAULT_BASE_WAIT, float)
    max_wait = _env_number("TRADINGAGENTS_RATE_LIMIT_MAX_WAIT", _DEFAULT_MAX_WAIT, float)

    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            if attempt >= max_retries or not is_retryable_rate_limit(exc):
                raise
            wait = _retry_after_seconds(exc)
            if wait is None:
                wait = base_wait * (2 ** attempt)
            wait = min(max(wait, 1.0), max_wait)
            # Up-only jitter: parallel runs (run_missing_today.sh fans out
            # 20-wide) all hit the limit together and must not all come
            # back in the same second.
            wait *= 1.0 + random.uniform(0.0, 0.1)
            attempt += 1
            logger.warning(
                "%s: provider rate limited (%s); waiting %.0fs before retry %d/%d",
                description, exc, wait, attempt, max_retries,
            )
            time.sleep(wait)
