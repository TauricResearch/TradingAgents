"""Vol Targeting strategy signal (§6.1 — Volatility Targeting / Position Sizing).

Suggests position size scaling based on target volatility vs realized volatility.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §6.1
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv

_TARGET_VOL = 0.15  # 15% annualized target


class VolTargetingStrategy(BaseStrategy):
    name = "Vol Targeting (§6.1)"
    roles = ["risk", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        df = get_ohlcv(ticker, date, context)
        if df is None or len(df) < 63:
            return None

        close = df["Close"].values[-63:]
        rv = float(np.std(np.diff(np.log(close))) * np.sqrt(252))
        if rv <= 0:
            return None

        # Scale factor: target / realized
        scale = _TARGET_VOL / rv
        scale = min(scale, 2.0)  # cap leverage at 2x

        # High vol → reduce position (bearish sizing), low vol → increase (bullish sizing)
        strength = max(-1.0, min(1.0, (scale - 1.0)))
        direction = "bullish" if scale > 1.1 else ("bearish" if scale < 0.9 else "neutral")

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"Vol target={_TARGET_VOL:.0%}, realized={rv:.1%}, scale={scale:.2f}x",
        )
