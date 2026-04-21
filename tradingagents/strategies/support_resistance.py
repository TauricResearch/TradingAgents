"""Support/Resistance strategy signal (§3.14 — Support and Resistance).

Identifies local min/max price levels and current proximity.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.14
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv


class SupportResistanceStrategy(BaseStrategy):
    name = "Support/Resistance (§3.14)"
    roles = ["market", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        df = get_ohlcv(ticker, date, context)
        if df is None or len(df) < 60:
            return None

        close = df["Close"].values[-60:]
        price = float(close[-1])
        high = float(np.max(close))
        low = float(np.min(close))
        rng = high - low
        if rng == 0:
            return None

        # Position within range: 0 = at support, 1 = at resistance
        pos = (price - low) / rng

        # Near resistance → bearish (expect pullback), near support → bullish
        strength = max(-1.0, min(1.0, (0.5 - pos) * 2))
        if pos > 0.85:
            direction, label = "bearish", "near resistance"
        elif pos < 0.15:
            direction, label = "bullish", "near support"
        else:
            direction, label = "neutral", "mid-range"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"{label}: price={price:.2f}, support={low:.2f}, resistance={high:.2f}, range_pos={pos:.0%}",
        )
