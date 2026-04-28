"""Tier-keyed process-wide LLM rate limiters.

Buckets are keyed by *tier* (``quick_think``, ``mid_think``, ``deep_think``,
``scanner``) rather than model name so a model swap inside a tier keeps the
same pacing. Useful when an upstream provider (e.g. Alibaba/DashScope via
OpenRouter) complains about burst rate even when average QPS is low.

Env vars (all optional — absence disables limiting for that tier):
    TRADINGAGENTS_<TIER>_RATE_LIMIT_RPS=<float>      # required to enable
    TRADINGAGENTS_<TIER>_RATE_LIMIT_BURST=<int>      # default 1 (strict pacing)
    TRADINGAGENTS_<TIER>_RATE_LIMIT_CHECK_INTERVAL=<float>  # default 0.1s

Example: cap mid_think to ~1 req/sec with no burst:
    TRADINGAGENTS_MID_THINK_RATE_LIMIT_RPS=1
"""

from __future__ import annotations

import threading
from typing import Any

from langchain_core.rate_limiters import InMemoryRateLimiter

from tradingagents.default_config import get_env_value

_VALID_TIERS = ("quick_think", "mid_think", "deep_think", "scanner")

_LOCK = threading.Lock()
_LIMITERS: dict[str, InMemoryRateLimiter] = {}
# Sentinel for tiers we've checked and confirmed have no env config.
_NO_LIMIT: Any = object()
_NEGATIVE: dict[str, Any] = {}


def _coerce_float(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _coerce_int(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def get_rate_limiter(tier: str) -> InMemoryRateLimiter | None:
    """Return a process-wide rate limiter for *tier*, or None if unconfigured.

    Lazy-instantiates one bucket per tier on first request. Subsequent calls
    return the same instance, so all LLM clients in the same tier share pacing
    across threads and pipelines.
    """
    if tier not in _VALID_TIERS:
        return None

    cached = _LIMITERS.get(tier)
    if cached is not None:
        return cached
    if _NEGATIVE.get(tier) is _NO_LIMIT:
        return None

    with _LOCK:
        cached = _LIMITERS.get(tier)
        if cached is not None:
            return cached
        if _NEGATIVE.get(tier) is _NO_LIMIT:
            return None

        rps_key = f"TRADINGAGENTS_{tier.upper()}_RATE_LIMIT_RPS"
        burst_key = f"TRADINGAGENTS_{tier.upper()}_RATE_LIMIT_BURST"
        check_key = f"TRADINGAGENTS_{tier.upper()}_RATE_LIMIT_CHECK_INTERVAL"

        rps = _coerce_float(get_env_value(rps_key))
        if rps is None or rps <= 0:
            _NEGATIVE[tier] = _NO_LIMIT
            return None

        burst = _coerce_int(get_env_value(burst_key)) or 1
        if burst < 1:
            burst = 1
        check_interval = _coerce_float(get_env_value(check_key)) or 0.1
        if check_interval <= 0:
            check_interval = 0.1

        limiter = InMemoryRateLimiter(
            requests_per_second=rps,
            check_every_n_seconds=check_interval,
            max_bucket_size=burst,
        )
        _LIMITERS[tier] = limiter
        return limiter


def reset_rate_limiters() -> None:
    """Drop all cached limiters. Tests use this between cases."""
    with _LOCK:
        _LIMITERS.clear()
        _NEGATIVE.clear()
