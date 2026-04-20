"""Volatility Targeting strategy signal (§6.5).

Scale position sizes to target a portfolio-level volatility budget.
Computes each position's marginal contribution to portfolio risk (MCTR)
and recommends sizing adjustments to keep portfolio vol near target.

Target vol: 15% annualized (typical balanced equity portfolio).
Positions contributing disproportionate vol → CONTRADICTS (reduce size).
Positions with low vol contribution → SUPPORTS (room to add).

Reference: Kakushadze & Serur §6.5 — "Volatility Targeting"
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal

_ANNUALIZE = np.sqrt(252)
_TARGET_VOL = 0.15  # 15% annualized portfolio vol target


class VolTargetingStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Position sizing recommendation based on target volatility. Tips: Reduces exposure in volatile markets, increases in calm markets. Not a directional signal — purely risk management. Apply after directional signals are determined."

    name = "vol_targeting"
    description = "Position sizing based on portfolio vol budget"
    target_analysts = ["risk"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        portfolio_tickers = kwargs.get("portfolio_tickers", [])
        if not portfolio_tickers or len(portfolio_tickers) < 2:
            return self._single_ticker(ticker, date, kwargs)

        end = pd.Timestamp(date)
        start = end - pd.DateOffset(days=180)
        start_str = start.strftime("%Y-%m-%d")
        end_str = (end + pd.DateOffset(days=1)).strftime("%Y-%m-%d")

        # Fetch returns for all portfolio tickers
        returns_dict: dict[str, pd.Series] = {}
        for t in portfolio_tickers:
            try:
                h = yf.Ticker(t).history(start=start_str, end=end_str)
                if len(h) >= 30:
                    returns_dict[t] = h["Close"].pct_change().dropna()
            except Exception:
                pass

        if ticker not in returns_dict or len(returns_dict) < 2:
            return self._single_ticker(ticker, date, kwargs)

        # Align returns to common dates
        df = pd.DataFrame(returns_dict).dropna()
        if len(df) < 30:
            return self._single_ticker(ticker, date, kwargs)

        n = len(df.columns)
        # Equal-weight assumption (no position sizes available at strategy level)
        weights = np.ones(n) / n
        cov = df.cov().values * 252  # annualized covariance

        # Portfolio vol
        port_var = weights @ cov @ weights
        port_vol = float(np.sqrt(port_var))

        # Marginal contribution to risk (MCTR) for target ticker
        ticker_idx = list(df.columns).index(ticker)
        mctr = (cov @ weights) / port_vol  # vector of MCTRs
        ticker_mctr = float(mctr[ticker_idx])

        # Contribution to risk (CTR) = weight × MCTR
        ticker_ctr = float(weights[ticker_idx] * ticker_mctr)
        # Proportional contribution
        pct_contribution = ticker_ctr / port_vol if port_vol > 0 else 1 / n

        # Vol scaling factor: how much to scale this position to hit target vol
        vol_scale = _TARGET_VOL / port_vol if port_vol > 0 else 1.0

        # Signal: is this position's vol contribution proportionate?
        fair_share = 1.0 / n
        if pct_contribution > fair_share * 1.5:
            signal, direction = "NEGATIVE", "CONTRADICTS"
            label = "overweight risk"
            sizing = "REDUCE"
        elif pct_contribution > fair_share * 1.2:
            signal, direction = "WEAK", "NEUTRAL"
            label = "slightly above fair share"
            sizing = "TRIM"
        elif pct_contribution < fair_share * 0.5:
            signal, direction = "STRONG", "SUPPORTS"
            label = "low risk contribution"
            sizing = "ADD"
        else:
            signal, direction = "MODERATE", "NEUTRAL"
            label = "proportionate risk"
            sizing = "HOLD"

        vol_label = "ABOVE" if port_vol > _TARGET_VOL else "BELOW" if port_vol < _TARGET_VOL * 0.8 else "ON"
        value_label = (
            f"MCTR {ticker_mctr:.1%}, {pct_contribution:.0%} of port risk ({label}) | "
            f"Port vol {port_vol:.1%} ({vol_label} {_TARGET_VOL:.0%} target) → {sizing}"
        )

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(ticker_mctr, 4),
            value_label=value_label,
            direction=direction,
            detail={
                "mctr": round(ticker_mctr, 4),
                "ctr": round(ticker_ctr, 4),
                "pct_contribution": round(pct_contribution, 4),
                "portfolio_vol": round(port_vol, 4),
                "target_vol": _TARGET_VOL,
                "vol_scale": round(vol_scale, 4),
                "sizing": sizing,
                "n_tickers": n,
            },
        )

    def _single_ticker(self, ticker: str, date: str, kwargs: dict) -> StrategySignal:
        """Fallback when no portfolio context — just compare ticker vol to target."""
        hist = kwargs.get("hist")
        if hist is None:
            end = pd.Timestamp(date)
            start = end - pd.DateOffset(days=180)
            try:
                hist = yf.Ticker(ticker).history(
                    start=start.strftime("%Y-%m-%d"),
                    end=(end + pd.DateOffset(days=1)).strftime("%Y-%m-%d"),
                )
            except Exception:
                return self._neutral(ticker, date)

        if hist is None or hist.empty or len(hist) < 30:
            return self._neutral(ticker, date)

        ret = hist["Close"].pct_change().dropna()
        vol = float(ret.iloc[-min(60, len(ret)):].std() * _ANNUALIZE)
        vol_scale = _TARGET_VOL / vol if vol > 0 else 1.0

        if vol > _TARGET_VOL * 1.5:
            signal, direction, sizing = "NEGATIVE", "CONTRADICTS", "REDUCE"
        elif vol > _TARGET_VOL:
            signal, direction, sizing = "WEAK", "NEUTRAL", "TRIM"
        elif vol < _TARGET_VOL * 0.5:
            signal, direction, sizing = "STRONG", "SUPPORTS", "ADD"
        else:
            signal, direction, sizing = "MODERATE", "NEUTRAL", "HOLD"

        value_label = f"Vol {vol:.1%} vs {_TARGET_VOL:.0%} target (scale {vol_scale:.2f}x) → {sizing}"

        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal=signal, value=round(vol, 4), value_label=value_label,
            direction=direction,
            detail={"ticker_vol": round(vol, 4), "target_vol": _TARGET_VOL,
                    "vol_scale": round(vol_scale, 4), "sizing": sizing},
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (insufficient data)",
            direction="NEUTRAL", detail={},
        )
