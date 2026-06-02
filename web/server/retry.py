"""Rate-aware retry helpers used by web.server.runner.

Pure functions, no I/O, no module state. Kept separate from the runner
so detection/parsing can be unit-tested without spinning up the queue
worker and so new providers can be supported by editing this file
alone.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional


# Substrings (case-insensitive) that identify a rate-limit exception class.
# Order doesn't matter — first match wins.
_RATE_LIMIT_CLASS_NAMES = (
    "ratelimiterror",
    "resourceexhausted",
    "quotaexceeded",
    "quotafailure",
    "toomanyrequests",
    "throttlingerror",
)

# Regex patterns matched against str(exc), in priority order.
# Patterns that need a qualifier word (e.g. 503 alone is too generic) include it
# inside the same regex.
_RATE_LIMIT_STRING_PATTERNS = (
    r"\b429\b",
    r"\bRESOURCE_EXHAUSTED\b",
    r'"code"\s*:\s*429',
    r'"type"\s*:\s*["\']rate_limit["\']',
    r"\b503\b.*\b(throttle|quota|rate[\s-]?limit)\b",
    r"\bquota[_ ]?exceeded\b",
)


def detect_rate_limit(exc: BaseException) -> bool:
    """True if exc looks like a 429 / quota error from any supported provider.

    Detection layers, cheapest first:
      1. Exception class name contains a known substring.
      2. str(exc) matches one of the known rate-limit regex patterns.
    """
    cls_name = type(exc).__name__.lower()
    for needle in _RATE_LIMIT_CLASS_NAMES:
        if needle in cls_name:
            return True
    msg = str(exc)
    for pattern in _RATE_LIMIT_STRING_PATTERNS:
        if re.search(pattern, msg, re.IGNORECASE):
            return True
    return False


# Cap provider hints that are unreasonably large (>1 hour). When a
# provider tells us to wait longer than that we treat it as a signal
# that we should give up and surface the failure, not stall the worker.
_MAX_RETRY_AFTER_S = 3600.0

# Pattern for Google's RetryInfo block: 'retryDelay': '46s' or '46.5s' or '1200ms'.
_GOOGLE_RETRY_DELAY_RE = re.compile(
    r"'retryDelay'\s*:\s*'(\d+(?:\.\d+)?)(ms|s)'"
)
# Pattern for HTTP Retry-After header in seconds.
_HTTP_RETRY_AFTER_SECONDS_RE = re.compile(
    r"Retry-After\s*:\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
# Pattern for HTTP Retry-After header as RFC 7231 HTTP-date.
_HTTP_RETRY_AFTER_DATE_RE = re.compile(
    r"Retry-After\s*:\s*"
    r"([A-Za-z]{3},\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{2}:\d{2}:\d{2}\s+GMT)",
    re.IGNORECASE,
)
# Pattern for "retry in 46s" / "retry after 30 seconds".
_GENERIC_RETRY_RE = re.compile(
    r"retry\s+(?:in|after)\s+(\d+(?:\.\d+)?)\s*(?:seconds?|s)",
    re.IGNORECASE,
)


def parse_retry_after(
    exc: BaseException, *, now: Optional[datetime] = None
) -> Optional[float]:
    """Seconds the provider asked us to wait, or None if not determinable.

    Recognised formats, in priority order:
      - Google RetryInfo block: 'retryDelay': '46s' | '46.5s' | '1200ms'
      - HTTP Retry-After header (seconds or RFC 7231 HTTP-date)
      - Generic "retry in 46s" / "retry after 30 seconds"
    """
    if now is None:
        now = datetime.now(timezone.utc)
    msg = str(exc)

    m = _GOOGLE_RETRY_DELAY_RE.search(msg)
    if m:
        value = float(m.group(1))
        unit = m.group(2)
        seconds = value / 1000.0 if unit == "ms" else value
        return _clamp_or_none(seconds)

    m = _HTTP_RETRY_AFTER_SECONDS_RE.search(msg)
    if m:
        return _clamp_or_none(float(m.group(1)))

    m = _HTTP_RETRY_AFTER_DATE_RE.search(msg)
    if m:
        try:
            target = parsedate_to_datetime(m.group(1))
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            delta = (target - now).total_seconds()
        except (TypeError, ValueError):
            return None
        return _clamp_or_none(delta)

    m = _GENERIC_RETRY_RE.search(msg)
    if m:
        return _clamp_or_none(float(m.group(1)))

    return None


def _clamp_or_none(seconds: float) -> Optional[float]:
    """Return seconds if 0 < seconds <= 3600, else None."""
    if 0 < seconds <= _MAX_RETRY_AFTER_S:
        return seconds
    return None


def compute_backoff(
    attempt: int,
    exc: BaseException,
    *,
    max_s: float = 60.0,
) -> float:
    """Seconds to sleep before retrying.

    Prefers ``parse_retry_after(exc)`` when present and within ``max_s``;
    otherwise falls back to ``min(max_s, 2 ** attempt) + uniform(0, 25%)``
    jitter, also capped at ``max_s``.

    ``attempt`` is 0-indexed (0 = first retry, 1 = second, ...).
    """
    hint = parse_retry_after(exc)
    if hint is not None and 0 < hint <= max_s:
        return hint
    base = min(max_s, 2 ** attempt)
    jitter = random.uniform(0, base * 0.25)
    return min(max_s, base + jitter)
