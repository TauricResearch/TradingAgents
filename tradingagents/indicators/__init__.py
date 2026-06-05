"""Technical indicators (the family-B ``compute_indicator`` tool).

Pure, deterministic functions over OHLCV bars — no LLM, no network. They are
the numbers the Technical desk reasons against, and the source of the ATR that
feeds entry/stop/take-profit and position sizing.

``core`` holds the math (operating on plain bar dicts); ``db`` reads bars from
the storage layer and returns ready-to-use indicator snapshots.
"""

from .core import (
    atr,
    compute_indicator,
    ema,
    high_low_52w,
    max_drawdown,
    rsi,
    sma,
    true_ranges,
)
from .db import atr_from_db, indicator_snapshot, recent_bars

__all__ = [
    "atr",
    "compute_indicator",
    "ema",
    "high_low_52w",
    "max_drawdown",
    "rsi",
    "sma",
    "true_ranges",
    "atr_from_db",
    "indicator_snapshot",
    "recent_bars",
]
