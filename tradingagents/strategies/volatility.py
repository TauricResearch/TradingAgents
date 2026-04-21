"""Volatility strategy signal (§3.4 — Volatility / Low-Vol Anomaly).

Computes realized volatility ranking and flags the low-volatility anomaly.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.4
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv


class VolatilityStrategy(BaseStrategy):
    name = "Volatility (§3.4)"
    roles = ["risk", "market", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        df = get_ohlcv(ticker, date, context)
        if df is None or len(df) < 63:
            return None

        close = df["Close"].values[-63:]
        returns = np.diff(np.log(close))
        vol = float(np.std(returns) * np.sqrt(252))

        # Low-vol anomaly: lower vol → mildly bullish signal
        # Map vol: 0.10→+0.5, 0.30→0, 0.60→-1.0
        strength = max(-1.0, min(1.0, (0.30 - vol) / 0.30))
        direction = "bullish" if strength > 0.1 else ("bearish" if strength < -0.1 else "neutral")

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"Realized vol (63d annualized): {vol:.1%}, low-vol anomaly {'active' if vol < 0.25 else 'inactive'}",
        )
