"""Mean Reversion strategy signal (§3.9 — Short-Term Reversal / Mean Reversion).

Z-score of current price vs rolling mean to detect overbought/oversold.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.9
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv


class MeanReversionStrategy(BaseStrategy):
    name = "Mean Reversion (§3.9)"
    roles = ["market", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        df = get_ohlcv(ticker, date, context)
        if df is None or len(df) < 60:
            return None

        close = df["Close"].values[-60:]
        mean = float(np.mean(close))
        std = float(np.std(close))
        if std == 0:
            return None

        z = (close[-1] - mean) / std
        # Mean reversion: high z → bearish (expect revert down), low z → bullish
        strength = max(-1.0, min(1.0, -z / 3.0))
        if z > 1.5:
            direction = "bearish"
            label = "overbought"
        elif z < -1.5:
            direction = "bullish"
            label = "oversold"
        else:
            direction = "neutral"
            label = "fair"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"Z-score: {z:+.2f} ({label}), 60d mean={mean:.2f}, price={close[-1]:.2f}",
        )
