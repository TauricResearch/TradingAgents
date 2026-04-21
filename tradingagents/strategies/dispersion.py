"""Dispersion strategy signal (§4.2 — Cross-Sectional Return Dispersion).

Measures cross-sectional return dispersion across sector ETFs to detect
high/low dispersion regimes (high dispersion favors stock-picking alpha).

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §4.2
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv

logger = logging.getLogger(__name__)

_SECTOR_ETFS = ["XLK", "XLV", "XLF", "XLY", "XLP", "XLE", "XLI", "XLB", "XLU", "XLRE", "XLC"]


class DispersionStrategy(BaseStrategy):
    name = "Dispersion (§4.2)"
    roles = ["researcher", "risk"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        returns: list[float] = []
        for etf in _SECTOR_ETFS:
            df = get_ohlcv(etf, date)
            if df is not None and len(df) >= 21:
                close = df["Close"].values
                returns.append((close[-1] - close[-21]) / close[-21])

        if len(returns) < 5:
            return None

        disp = float(np.std(returns))
        # High dispersion → more alpha opportunity → mildly bullish for active strategies
        # Normalize: 0.02 = low, 0.08 = high
        strength = max(-1.0, min(1.0, (disp - 0.05) / 0.05))
        if disp > 0.06:
            direction, label = "bullish", "high dispersion (stock-picking favored)"
        elif disp < 0.03:
            direction, label = "bearish", "low dispersion (index-like)"
        else:
            direction, label = "neutral", "moderate dispersion"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"{label}: sector return dispersion={disp:.4f}",
        )
