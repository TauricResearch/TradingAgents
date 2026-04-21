"""Residual Momentum strategy signal (§3.7 — Residual Momentum).

Momentum after removing market beta exposure, isolating stock-specific trend.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.7
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv


class ResidualMomentumStrategy(BaseStrategy):
    name = "Residual Momentum (§3.7)"
    roles = ["market", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        df = get_ohlcv(ticker, date, context)
        spy_df = get_ohlcv("SPY", date)
        if df is None or spy_df is None or len(df) < 252 or len(spy_df) < 252:
            return None

        # Daily log returns over past 252 days
        stock_ret = np.diff(np.log(df["Close"].values[-253:]))
        mkt_ret = np.diff(np.log(spy_df["Close"].values[-253:]))
        if len(stock_ret) != len(mkt_ret):
            return None

        # OLS beta: cov(stock, mkt) / var(mkt)
        mkt_var = float(np.var(mkt_ret))
        if mkt_var == 0:
            return None
        beta = float(np.cov(stock_ret, mkt_ret)[0, 1]) / mkt_var

        # Residual returns = stock - beta * market
        residuals = stock_ret - beta * mkt_ret
        # Cumulative residual momentum (skip last 21 days for reversal)
        res_mom = float(np.sum(residuals[:-21]))

        strength = max(-1.0, min(1.0, res_mom * 5))
        direction = "bullish" if strength > 0.05 else ("bearish" if strength < -0.05 else "neutral")

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"Residual momentum (beta-adj): {res_mom:+.4f}, beta={beta:.2f}",
        )
