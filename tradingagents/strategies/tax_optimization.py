"""Tax Optimization strategy signal (§7.1 — Tax-Loss Harvesting).

Scores tax-loss harvesting opportunity based on unrealized loss from recent highs.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §7.1
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv


class TaxOptimizationStrategy(BaseStrategy):
    name = "Tax Optimization (§7.1)"
    roles = ["risk", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        df = get_ohlcv(ticker, date, context)
        if df is None or len(df) < 252:
            return None

        close = df["Close"].values[-252:]
        price = float(close[-1])
        high_252 = float(np.max(close))
        if high_252 <= 0:
            return None

        drawdown = (price - high_252) / high_252  # negative when below high

        # Larger drawdown → stronger harvesting opportunity
        if drawdown > -0.05:
            return None  # no meaningful loss to harvest

        # Map drawdown: -5% → 0, -30%+ → 1.0 opportunity score
        opportunity = min(1.0, abs(drawdown) / 0.30)
        # Bearish signal: suggests selling to harvest loss
        strength = round(-opportunity, 4)

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=strength,
            direction="bearish",
            detail=f"Tax-loss harvest opportunity: drawdown={drawdown:.1%} from 252d high={high_252:.2f}",
        )
