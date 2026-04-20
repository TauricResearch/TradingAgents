"""Trend Following strategy signal (§3.10 — Time-Series Momentum / Trend Following).

Multi-timeframe trend strength using short, medium, and long lookbacks.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.10
"""

from __future__ import annotations

from typing import Any

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv


class TrendFollowingStrategy(BaseStrategy):
    name = "Trend Following (§3.10)"
    roles = ["market", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        df = get_ohlcv(ticker, date, context)
        if df is None or len(df) < 252:
            return None

        close = df["Close"].values
        scores: list[float] = []
        details: list[str] = []

        for label, period in [("21d", 21), ("63d", 63), ("252d", 252)]:
            ret = (close[-1] - close[-period]) / close[-period]
            s = max(-1.0, min(1.0, ret * (252 / period) ** 0.5))  # vol-scale
            scores.append(s)
            details.append(f"{label}={ret:+.1%}")

        strength = round(sum(scores) / len(scores), 4)
        strength = max(-1.0, min(1.0, strength))
        direction = "bullish" if strength > 0.05 else ("bearish" if strength < -0.05 else "neutral")

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=strength,
            direction=direction,
            detail=f"Multi-TF trend: {', '.join(details)}",
        )
