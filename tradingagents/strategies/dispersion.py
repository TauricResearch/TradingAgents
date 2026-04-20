"""Dispersion Trading strategy signal (§6.3).

Compares index (SPY) realized volatility to the average realized volatility
of its constituents (portfolio tickers). High dispersion (constituent vol >>
index vol) means low correlation → stock-picking adds value. Low dispersion
means high correlation → macro/beta dominates.

Reference: Kakushadze & Serur §6.3 — "Dispersion Trading"
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal

_ANNUALIZE = np.sqrt(252)
_INDEX = "SPY"


class DispersionStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: High cross-sectional dispersion = stock-picker's market (alpha opportunities). Tips: Low dispersion = index-like returns, favor passive. Regime indicator, not directional. Combine with factor signals — they work better in high-dispersion environments."

    name = "dispersion"
    description = "Index vs constituent vol for correlation regime detection"
    target_analysts = ["risk"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        end = pd.Timestamp(date)
        start = end - pd.DateOffset(days=180)
        start_str = start.strftime("%Y-%m-%d")
        end_str = (end + pd.DateOffset(days=1)).strftime("%Y-%m-%d")

        try:
            idx_hist = yf.Ticker(_INDEX).history(start=start_str, end=end_str)
            tk_hist = kwargs.get("hist")
            if tk_hist is None:
                tk_hist = yf.Ticker(ticker).history(start=start_str, end=end_str)
        except Exception:
            return self._neutral(ticker, date)

        if idx_hist is None or len(idx_hist) < 30 or tk_hist is None or len(tk_hist) < 30:
            return self._neutral(ticker, date)

        idx_ret = idx_hist["Close"].pct_change().dropna().iloc[-60:]
        tk_ret = tk_hist["Close"].pct_change().dropna().iloc[-60:]

        if len(idx_ret) < 20 or len(tk_ret) < 20:
            return self._neutral(ticker, date)

        idx_vol = float(idx_ret.std() * _ANNUALIZE)
        tk_vol = float(tk_ret.std() * _ANNUALIZE)

        # Dispersion ratio: ticker vol / index vol
        # High ratio → low implied correlation → stock-picking regime
        disp_ratio = tk_vol / idx_vol if idx_vol > 0 else 1.0

        # Implied correlation estimate: ρ ≈ (σ_index² / avg(σ_i²))
        # Simplified: just use ratio as proxy
        implied_corr = min(1.0, idx_vol / tk_vol) if tk_vol > 0 else 1.0

        if disp_ratio > 2.0:
            signal, direction = "STRONG", "SUPPORTS"
            regime = "HIGH DISPERSION — stock-picking adds value"
        elif disp_ratio > 1.3:
            signal, direction = "MODERATE", "SUPPORTS"
            regime = "MODERATE DISPERSION — selective alpha possible"
        elif disp_ratio < 0.8:
            signal, direction = "WEAK", "CONTRADICTS"
            regime = "LOW DISPERSION — macro/beta dominates"
        else:
            signal, direction = "NEUTRAL", "NEUTRAL"
            regime = "NORMAL DISPERSION"

        value_label = (
            f"Dispersion {disp_ratio:.2f}x (ticker vol {tk_vol:.1%} vs {_INDEX} {idx_vol:.1%}) | "
            f"Implied corr ~{implied_corr:.2f} | {regime}"
        )

        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal=signal, value=round(disp_ratio, 4), value_label=value_label,
            direction=direction,
            detail={
                "dispersion_ratio": round(disp_ratio, 4),
                "ticker_vol": round(tk_vol, 4),
                "index_vol": round(idx_vol, 4),
                "implied_correlation": round(implied_corr, 4),
                "regime": regime,
                "index": _INDEX,
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (insufficient data)",
            direction="NEUTRAL", detail={},
        )
