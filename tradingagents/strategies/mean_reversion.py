"""Mean Reversion strategy signal (§3.9).

Z-score of current price vs rolling mean over trailing 60 trading days.
Overbought (Z > 1.5) suggests pullback risk; oversold (Z < -1.5) suggests
bounce potential. Useful for entry/exit timing.

Reference: Kakushadze & Serur §3.9 — "Short-Term Mean Reversion"
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal

_WINDOW = 60  # trading days for rolling mean/std


class MeanReversionStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Identifies overbought/oversold conditions for counter-trend entries. Tips: Do NOT fade strong trends — mean reversion fails in trending markets. Best for range-bound stocks. Combine with support/resistance levels for entry timing. Z-score >2 or <-2 is high conviction."

    name = "mean_reversion"
    description = "Z-score vs rolling mean, overbought/oversold"
    target_analysts = ["technical"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        hist = kwargs.get("hist")
        if hist is None:
            end = pd.Timestamp(date)
            start = end - pd.DateOffset(days=120)
            hist = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=(end + pd.DateOffset(days=1)).strftime("%Y-%m-%d"),
            )

        if hist.empty or len(hist) < _WINDOW:
            return self._neutral(ticker, date)

        close = hist["Close"]
        rolling_mean = float(close.iloc[-_WINDOW:].mean())
        rolling_std = float(close.iloc[-_WINDOW:].std())

        if rolling_std == 0:
            return self._neutral(ticker, date)

        current = float(close.iloc[-1])
        z_score = (current - rolling_mean) / rolling_std

        # Classify
        if z_score > 2.0:
            signal, label, direction = "STRONG", "overbought", "CONTRADICTS"
        elif z_score > 1.5:
            signal, label, direction = "MODERATE", "overbought", "CONTRADICTS"
        elif z_score < -2.0:
            signal, label, direction = "STRONG", "oversold", "SUPPORTS"
        elif z_score < -1.5:
            signal, label, direction = "MODERATE", "oversold", "SUPPORTS"
        elif abs(z_score) < 0.5:
            signal, label, direction = "NEUTRAL", "near mean", "NEUTRAL"
        elif z_score > 0:
            signal, label, direction = "WEAK", "above mean", "NEUTRAL"
        else:
            signal, label, direction = "WEAK", "below mean", "NEUTRAL"

        # Percentile rank within rolling window
        pct_rank = float((close.iloc[-_WINDOW:] < current).mean())

        value_label = f"Z={z_score:+.2f} ({label}, {pct_rank:.0%} percentile)"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(z_score, 4),
            value_label=value_label,
            direction=direction,
            detail={
                "z_score": round(z_score, 4),
                "rolling_mean": round(rolling_mean, 2),
                "rolling_std": round(rolling_std, 2),
                "current_price": round(current, 2),
                "percentile_rank": round(pct_rank, 4),
                "window": _WINDOW,
                "overbought": z_score > 1.5,
                "oversold": z_score < -1.5,
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (insufficient data)",
            direction="NEUTRAL", detail={},
        )
