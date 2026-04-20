"""Implied Volatility strategy signal (§3.5 — Volatility Premium/Discount).

Compares implied volatility to realized volatility to detect IV premium or discount.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.5
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv, get_info

logger = logging.getLogger(__name__)


class ImpliedVolStrategy(BaseStrategy):
    name = "Implied Volatility (§3.5)"
    roles = ["risk", "market", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        df = get_ohlcv(ticker, date, context)
        if df is None or len(df) < 63:
            return None

        info = get_info(ticker, context)
        iv = info.get("impliedVolatility") if info else None
        if iv is None or iv <= 0:
            return None

        # Realized vol (63d annualized)
        close = df["Close"].values[-63:]
        rv = float(np.std(np.diff(np.log(close))) * np.sqrt(252))
        if rv <= 0:
            return None

        # IV premium: IV > RV → options expensive → bearish bias (mean-revert expectation)
        premium = (iv - rv) / rv
        strength = max(-1.0, min(1.0, -premium))  # high premium → bearish
        direction = "bearish" if premium > 0.2 else ("bullish" if premium < -0.2 else "neutral")
        label = "premium" if premium > 0 else "discount"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"IV={iv:.1%} vs RV={rv:.1%}, {label}={premium:+.1%}",
        )
