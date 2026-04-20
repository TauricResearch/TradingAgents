"""Residual Momentum strategy signal (§3.7).

Momentum after removing market (SPY) beta — isolates stock-specific
momentum from broad market moves. A stock riding the market up has
low residual momentum; one outperforming its beta-adjusted benchmark
has high residual momentum.

Reference: Kakushadze & Serur §3.7 — "Residual Momentum"
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal


class ResidualMomentumStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Captures stock-specific momentum after removing market/sector effects. Tips: More predictive than raw momentum for stock selection. Positive residual momentum = stock outperforming its expected return. Combine with fundamentals to distinguish skill from luck."

    name = "residual_momentum"
    description = "Stock-specific momentum after removing market beta"
    target_analysts = ["technical"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        end = pd.Timestamp(date)
        start = end - pd.DateOffset(months=13)
        start_str = start.strftime("%Y-%m-%d")
        end_str = (end + pd.DateOffset(days=1)).strftime("%Y-%m-%d")

        hist = kwargs.get("hist")
        if hist is None:
            hist = yf.Ticker(ticker).history(start=start_str, end=end_str)
        if hist.empty or len(hist) < 60:
            return self._neutral(ticker, date)

        # Fetch market benchmark (SPY)
        try:
            mkt = yf.Ticker("SPY").history(start=start_str, end=end_str)
        except Exception:
            return self._neutral(ticker, date)
        if mkt.empty or len(mkt) < 60:
            return self._neutral(ticker, date)

        # Align dates and compute daily returns
        stock_ret = hist["Close"].pct_change().dropna()
        mkt_ret = mkt["Close"].pct_change().dropna()
        aligned = pd.DataFrame({"stock": stock_ret, "market": mkt_ret}).dropna()
        if len(aligned) < 60:
            return self._neutral(ticker, date)

        # OLS regression: stock = alpha + beta * market + residual
        x = aligned["market"].values
        y = aligned["stock"].values
        x_mean = x.mean()
        beta = np.sum((x - x_mean) * (y - y.mean())) / np.sum((x - x_mean) ** 2)
        alpha = y.mean() - beta * x_mean
        residuals = y - (alpha + beta * x)

        # Residual momentum: cumulative residual return over lookback (skip last month)
        n = len(residuals)
        skip_1m = min(22, n // 4)
        if n <= skip_1m:
            return self._neutral(ticker, date)

        # 12-1 residual momentum (skip last month to avoid reversal)
        cum_residual = float(np.sum(residuals[:-skip_1m]))
        cum_residual_full = float(np.sum(residuals))
        residual_vol = float(np.std(residuals)) if len(residuals) > 1 else 1.0

        # T-stat of residual momentum
        t_stat = cum_residual / (residual_vol * np.sqrt(n - skip_1m)) if residual_vol > 0 else 0.0

        # Signal strength based on t-stat
        if t_stat > 2.0:
            signal = "STRONG"
        elif t_stat > 1.0:
            signal = "MODERATE"
        elif t_stat > -1.0:
            signal = "WEAK"
        else:
            signal = "NEGATIVE"

        direction = "SUPPORTS" if t_stat > 1.0 else "CONTRADICTS" if t_stat < -1.0 else "NEUTRAL"

        value_label = f"t={t_stat:+.2f}, β={beta:.2f}, residual={cum_residual:+.1%}"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(t_stat, 4),
            value_label=value_label,
            direction=direction,
            detail={
                "beta": round(beta, 4),
                "alpha_daily": round(alpha, 6),
                "cum_residual": round(cum_residual, 4),
                "cum_residual_full": round(cum_residual_full, 4),
                "residual_vol": round(residual_vol, 6),
                "t_stat": round(t_stat, 4),
                "n_days": n,
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (insufficient data)",
            direction="NEUTRAL", detail={},
        )
