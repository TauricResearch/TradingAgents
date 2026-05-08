from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .models import BacktestResult, DIRECTION_MAP

logger = logging.getLogger(__name__)


def business_days_between(start_date: str, end_date: str) -> int:
    """Count business days between two ISO-8601 date strings (exclusive of end)."""
    return int(np.busday_count(start_date, end_date))


def get_holding_days(
    current_date: str,
    next_signal_date: Optional[str],
    hold_days_override: Optional[int],
    max_fallback_days: int = 21,
) -> int:
    """Return the number of trading days to hold a signal for return measurement."""
    if hold_days_override is not None:
        return hold_days_override
    if next_signal_date is not None:
        return max(1, business_days_between(current_date, next_signal_date))
    return max_fallback_days


def is_win(direction: int, raw_return: float) -> Optional[bool]:
    """Return True if direction matched return sign, None for HOLD or tie."""
    if direction == 0:
        return None
    if raw_return == 0.0:
        return None
    return (direction > 0) == (raw_return > 0)
