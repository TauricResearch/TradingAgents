"""Alpha Combo strategy signal (§3.15 — Alpha Combination / Factor Ensemble).

Ensemble of top-performing factor signals: momentum, value, mean-reversion.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.15
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv, get_info


class AlphaComboStrategy(BaseStrategy):
    name = "Alpha Combo (§3.15)"
    roles = ["researcher", "risk"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        df = get_ohlcv(ticker, date, context)
        if df is None or len(df) < 252:
            return None

        close = df["Close"].values
        factors: list[float] = []
        details: list[str] = []

        # Momentum: 12-1 month return
        mom = (close[-21] - close[-252]) / close[-252]
        factors.append(max(-1.0, min(1.0, mom)))
        details.append(f"mom={mom:+.2%}")

        # Mean reversion: 20d z-score (inverted)
        recent = close[-20:]
        z = (recent[-1] - float(np.mean(recent))) / max(float(np.std(recent)), 1e-8)
        factors.append(max(-1.0, min(1.0, -z / 3.0)))
        details.append(f"mr_z={z:+.1f}")

        # Value: inverse PE if available
        info = get_info(ticker, context)
        if info:
            pe = info.get("trailingPE")
            if pe and pe > 0:
                val = min(1.0 / pe / 0.15, 1.0) * 2 - 1
                factors.append(max(-1.0, min(1.0, val)))
                details.append(f"val_pe={pe:.1f}")

        strength = round(sum(factors) / len(factors), 4)
        strength = max(-1.0, min(1.0, strength))
        direction = "bullish" if strength > 0.05 else ("bearish" if strength < -0.05 else "neutral")

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=strength,
            direction=direction,
            detail=f"Alpha ensemble ({len(factors)} factors): {', '.join(details)}",
        )
