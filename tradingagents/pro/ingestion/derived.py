"""Deterministic derived-feature math (Constraint 2: code computes, LLMs read).

Pure functions with no I/O so they are trivially unit-testable and reusable
by both the live snapshot builder and the backtester.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

from tradingagents.contracts import OHLCVBar


def pearson_correlation(a: Sequence[float], b: Sequence[float]) -> float:
    """Pearson correlation of two equal-length series.

    Raises ValueError on length mismatch or fewer than 3 points — a
    correlation from 2 points is always ±1 and would mislead agents.
    """
    if len(a) != len(b):
        raise ValueError(f"series length mismatch: {len(a)} vs {len(b)}")
    if len(a) < 3:
        raise ValueError(f"need at least 3 points, got {len(a)}")
    mean_a = math.fsum(a) / len(a)
    mean_b = math.fsum(b) / len(b)
    cov = math.fsum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True))
    var_a = math.fsum((x - mean_a) ** 2 for x in a)
    var_b = math.fsum((y - mean_b) ** 2 for y in b)
    if var_a == 0 or var_b == 0:
        raise ValueError("zero-variance series has no defined correlation")
    return cov / math.sqrt(var_a * var_b)


def orderbook_imbalance(
    bids: Sequence[tuple[float, float]], asks: Sequence[tuple[float, float]]
) -> float:
    """Depth imbalance in [-1, 1]: +1 all-bid, -1 all-ask.

    Inputs are (price, quantity) levels; only quantities matter for the
    classic volume-imbalance measure.
    """
    bid_qty = math.fsum(q for _, q in bids)
    ask_qty = math.fsum(q for _, q in asks)
    total = bid_qty + ask_qty
    if total == 0:
        raise ValueError("empty order book: no bid or ask quantity")
    return (bid_qty - ask_qty) / total


def bars_to_dataframe(bars: Sequence[OHLCVBar]) -> pd.DataFrame:
    """Convert contract bars to the OHLCV DataFrame shape stockstats expects."""
    bars = list(bars)
    if not bars:
        raise ValueError("no bars supplied")
    frame = pd.DataFrame(
        {
            "date": [b.start for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        }
    )
    return frame.sort_values("date").reset_index(drop=True)
