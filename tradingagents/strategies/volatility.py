"""Low-Volatility Anomaly strategy signal (§3.4).

Realized volatility ranking — annualized from daily returns over trailing
60 trading days. Low-vol stocks historically outperform on risk-adjusted
basis (low-vol anomaly). Flags high-vol positions for position sizing
and low-vol for potential overweight.

Reference: Kakushadze & Serur §3.4 — "Low-Volatility Investing"
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal

# Annualization factor (√252 trading days)
_ANNUALIZE = np.sqrt(252)


class VolatilityStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Low-vol stocks historically outperform on risk-adjusted basis (low-vol anomaly). Tips: Signal inverts during market stress — low-vol stocks can gap down sharply. Use as position sizing input, not directional signal. Combine with momentum for 'low-vol + trending' filter."

    name = "volatility"
    description = "Realized vol ranking, low-vol anomaly flag"
    target_analysts = ["risk"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        hist = kwargs.get("hist")
        if hist is None:
            end = pd.Timestamp(date)
            start = end - pd.DateOffset(days=120)  # ~60 trading days + buffer
            hist = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=(end + pd.DateOffset(days=1)).strftime("%Y-%m-%d"),
            )

        if hist.empty or len(hist) < 20:
            return self._neutral(ticker, date)

        close = hist["Close"]
        returns = close.pct_change().dropna()
        if len(returns) < 20:
            return self._neutral(ticker, date)

        # Realized vol (annualized) — trailing 60 days or available
        trail = returns.iloc[-min(60, len(returns)):]
        realized_vol = float(trail.std() * _ANNUALIZE)

        # Compare to SPY as market benchmark
        spy_vol = self._spy_vol(date, kwargs)

        # Vol ratio: >1 means more volatile than market
        vol_ratio = realized_vol / spy_vol if spy_vol > 0 else 1.0

        # Low-vol anomaly flag
        low_vol = vol_ratio < 0.8
        high_vol = vol_ratio > 1.5

        # Signal: low-vol = SUPPORTS overweight (anomaly), high-vol = CONTRADICTS (risk)
        if low_vol:
            signal, label, direction = "STRONG", "low-vol anomaly", "SUPPORTS"
        elif vol_ratio <= 1.0:
            signal, label, direction = "MODERATE", "below-market vol", "SUPPORTS"
        elif vol_ratio <= 1.5:
            signal, label, direction = "WEAK", "above-market vol", "NEUTRAL"
        else:
            signal, label, direction = "NEGATIVE", "high-vol", "CONTRADICTS"

        # Rank within portfolio if provided
        rank, total = None, None
        portfolio_tickers = kwargs.get("portfolio_tickers", [])
        if portfolio_tickers and len(portfolio_tickers) > 1:
            vols = {}
            for t in portfolio_tickers:
                if t == ticker:
                    vols[t] = realized_vol
                else:
                    try:
                        end_ts = pd.Timestamp(date)
                        t_hist = yf.Ticker(t).history(
                            start=(end_ts - pd.DateOffset(days=120)).strftime("%Y-%m-%d"),
                            end=(end_ts + pd.DateOffset(days=1)).strftime("%Y-%m-%d"),
                        )
                        if len(t_hist) >= 20:
                            t_ret = t_hist["Close"].pct_change().dropna()
                            vols[t] = float(t_ret.iloc[-min(60, len(t_ret)):].std() * _ANNUALIZE)
                    except Exception:
                        pass
            if vols:
                # Rank by vol ascending (lowest vol = rank 1 = best for low-vol anomaly)
                ranked = sorted(vols, key=lambda k: vols[k])
                rank = ranked.index(ticker) + 1 if ticker in ranked else None
                total = len(ranked)

        rank_label = f" (rank {rank}/{total})" if rank and total else ""
        value_label = f"{realized_vol:.1%} ann. vol, {vol_ratio:.2f}x market ({label}){rank_label}"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(realized_vol, 4),
            value_label=value_label,
            direction=direction,
            detail={
                "realized_vol": round(realized_vol, 4),
                "spy_vol": round(spy_vol, 4),
                "vol_ratio": round(vol_ratio, 4),
                "low_vol_anomaly": low_vol,
                "high_vol": high_vol,
                "rank": rank,
                "total": total,
            },
        )

    def _spy_vol(self, date: str, kwargs: dict) -> float:
        """Get SPY realized vol as market benchmark."""
        spy_hist = kwargs.get("spy_hist")
        if spy_hist is None:
            try:
                end = pd.Timestamp(date)
                spy_hist = yf.Ticker("SPY").history(
                    start=(end - pd.DateOffset(days=120)).strftime("%Y-%m-%d"),
                    end=(end + pd.DateOffset(days=1)).strftime("%Y-%m-%d"),
                )
            except Exception:
                return 0.16  # ~16% long-run avg
        if spy_hist is None or spy_hist.empty or len(spy_hist) < 20:
            return 0.16
        ret = spy_hist["Close"].pct_change().dropna()
        trail = ret.iloc[-min(60, len(ret)):]
        return float(trail.std() * _ANNUALIZE)

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (insufficient data)",
            direction="NEUTRAL", detail={},
        )
