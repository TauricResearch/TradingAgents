"""Momentum strategy signal (§3.1 — Cross-Sectional Momentum).

Computes 12-1 month price momentum: cumulative return over months [-12, -1]
skipping the most recent month to avoid short-term reversal.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.1
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv


class MomentumStrategy(BaseStrategy):
    name = "Momentum (§3.1)"
    roles = ["market", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        df = get_ohlcv(ticker, date, context)
        if df is None or len(df) < 252:
            return None

        close = df["Close"].values
        # 12-1 month momentum: return from 252 days ago to 21 days ago
        ret = (close[-21] - close[-252]) / close[-252]

        strength = max(-1.0, min(1.0, ret))  # clamp
        direction = "bullish" if strength > 0.05 else ("bearish" if strength < -0.05 else "neutral")

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"12-1 month return: {ret:+.2%}",
        )
