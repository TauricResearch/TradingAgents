from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

DIRECTION_MAP: dict[str, int] = {
    "Buy": +1, "Overweight": +1,
    "Hold": 0,
    "Underweight": -1, "Sell": -1,
}


def derive_direction(rating: Optional[str]) -> Optional[int]:
    """Return None for missing or unrecognised ratings — not 0 (which means Hold)."""
    if rating is None:
        return None
    return DIRECTION_MAP.get(rating, None)


@dataclass
class BacktestResult:
    ticker: str
    trade_date: str                       # ISO-8601 "YYYY-MM-DD" — always this format
    rating: Optional[str] = None          # 5-tier PM output: Buy/Overweight/Hold/Underweight/Sell
    direction: Optional[int] = None       # +1, 0, -1, or None for failed/unknown
    raw_output: str = ""                  # full Portfolio Manager markdown
    run_duration_seconds: float = 0.0
    error: Optional[str] = None           # exception message; rating/direction are None when set
