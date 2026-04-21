"""Moving Average strategy signal (§3.11-3.13 — Moving Average Crossovers).

SMA crossover signals: 50/200 golden cross / death cross.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.11-3.13
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv


class MovingAverageStrategy(BaseStrategy):
    name = "Moving Average (§3.11-3.13)"
    roles = ["market", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        df = get_ohlcv(ticker, date, context)
        if df is None or len(df) < 200:
            return None

        close = df["Close"].values
        sma50 = float(np.mean(close[-50:]))
        sma200 = float(np.mean(close[-200:]))

        if sma200 == 0:
            return None

        spread = (sma50 - sma200) / sma200
        strength = max(-1.0, min(1.0, spread * 5))

        if sma50 > sma200:
            direction = "bullish"
            label = "golden cross" if spread > 0.02 else "SMA50 > SMA200"
        elif sma50 < sma200:
            direction = "bearish"
            label = "death cross" if spread < -0.02 else "SMA50 < SMA200"
        else:
            direction = "neutral"
            label = "converged"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"{label}: SMA50={sma50:.2f}, SMA200={sma200:.2f}, spread={spread:+.2%}",
        )
