"""Earnings Momentum strategy signal (§3.2 — Earnings Momentum / SUE).

Computes Standardized Unexpected Earnings (SUE) from the most recent
earnings surprise relative to trailing EPS standard deviation.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.2
"""

from __future__ import annotations

from typing import Any

from .base import BaseStrategy, StrategySignal
from ._data import get_info


class EarningsMomentumStrategy(BaseStrategy):
    name = "Earnings Momentum (§3.2)"
    roles = ["fundamentals", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        info = get_info(ticker, context)
        if not info:
            return None

        trailing_eps = info.get("trailingEps")
        forward_eps = info.get("forwardEps")
        if trailing_eps is None or forward_eps is None or trailing_eps == 0:
            return None

        # SUE proxy: (forward - trailing) / |trailing|
        sue = (forward_eps - trailing_eps) / abs(trailing_eps)
        strength = max(-1.0, min(1.0, sue))
        direction = "bullish" if strength > 0.05 else ("bearish" if strength < -0.05 else "neutral")

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"SUE proxy (fwd-trail)/|trail|: {sue:+.2f} (trail={trailing_eps}, fwd={forward_eps})",
        )
