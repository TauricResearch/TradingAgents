"""Yfinance-backed historical price bars for the dashboard's chart feature.

Wraps ``yf.Ticker.history`` with an in-memory TTL cache and exposes
range resolution (preset → start/end/interval). The HTTP layer in
:mod:`web.server.app` is a thin adapter around :func:`get_history`.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import yfinance as yf


log = logging.getLogger(__name__)


#: Window size for each preset. "all" is the 1y cap per the spec.
_PRESET_WINDOWS: dict[str, timedelta] = {
    "1d": timedelta(days=1),
    "5d": timedelta(days=5),
    "1mo": timedelta(days=30),
    "3mo": timedelta(days=90),
    "6mo": timedelta(days=180),
    "1y": timedelta(days=365),
    "all": timedelta(days=365),
}


def now_utc() -> datetime:
    """Pluggable clock for tests."""
    return datetime.now(timezone.utc)


def resolve_range(
    preset: str,
    *,
    earliest_started_at: Optional[datetime],
) -> tuple[datetime, datetime, str]:
    """Translate a user preset into a concrete (start, end, interval).

    Args:
        preset: One of ``{1d, 5d, 1mo, 3mo, 6mo, 1y, all, auto}``.
        earliest_started_at: The earliest run's ``started_at`` for
            ``preset="auto"``. ``None`` for all other presets. Required
            for ``auto`` — the function raises :class:`ValueError` if
            missing.

    Returns:
        ``(start, end, interval)`` where ``interval`` is one of
        ``{"1m", "1h", "1d"}`` chosen by the span between start and end.

    Raises:
        ValueError: on an unknown preset, or on ``auto`` with no runs.
    """
    if preset == "auto":
        if earliest_started_at is None:
            raise ValueError("auto preset requires earliest_started_at (no runs)")
        start = earliest_started_at
        end = now_utc()
    else:
        if preset not in _PRESET_WINDOWS:
            raise ValueError(f"invalid preset: {preset!r}")
        end = now_utc()
        start = end - _PRESET_WINDOWS[preset]

    interval = _interval_for_span(end - start)
    return start, end, interval


def _interval_for_span(span: timedelta) -> str:
    """Pick the yfinance interval that fits the span without oversampling.

    ≤ 7d → 1m   (highest resolution; 1m is fresh for 7 days)
    ≤ 60d → 1h  (1m caps at 7d; 1h caps at 730d)
    > 60d → 1d  (1h is wasteful; 1d is fine for multi-month views)
    """
    if span <= timedelta(days=7):
        return "1m"
    if span <= timedelta(days=60):
        return "1h"
    return "1d"
