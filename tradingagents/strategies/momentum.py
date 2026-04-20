"""Price Momentum strategy signal (§3.1).

12-month return minus last month (12-1 momentum) to capture medium-term
trend while avoiding short-term reversal. Rank within portfolio provided
via kwargs['portfolio_tickers'].

Reference: Kakushadze & Serur §3.1 — "Cross-Sectional Momentum"
"""

from __future__ import annotations

import yfinance as yf
import pandas as pd

from tradingagents.strategies.base import BaseStrategy, StrategySignal


class MomentumStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Strongest when confirmed by fundamentals — high momentum + improving earnings = high conviction. Tips: Momentum crashes in regime changes (e.g. rate hikes); combine with volatility signal. Weakens in late-cycle markets. 12-1 month window avoids short-term reversal noise."

    name = "momentum"
    description = "12-1 month price momentum score + portfolio rank"
    target_analysts = ["technical"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        hist = kwargs.get("hist")
        if hist is None:
            end = pd.Timestamp(date)
            start = end - pd.DateOffset(months=13)
            hist = yf.Ticker(ticker).history(start=start.strftime("%Y-%m-%d"), end=(end + pd.DateOffset(days=1)).strftime("%Y-%m-%d"))

        if hist.empty or len(hist) < 22:
            return self._neutral(ticker, date)

        close = hist["Close"]
        # 12-month return
        if len(close) >= 252:
            ret_12m = (close.iloc[-1] / close.iloc[-252]) - 1
        else:
            ret_12m = (close.iloc[-1] / close.iloc[0]) - 1

        # Last month return (skip it — 12-1 momentum)
        ret_1m = (close.iloc[-1] / close.iloc[-min(22, len(close))]) - 1

        momentum_score = ret_12m - ret_1m

        # Reversal risk: last month was extreme (>2σ of monthly returns)
        monthly = close.resample("ME").last().pct_change().dropna()
        reversal_risk = False
        if len(monthly) >= 3:
            reversal_risk = abs(ret_1m) > monthly.std() * 2

        # Signal strength
        if momentum_score > 0.20:
            signal = "STRONG"
        elif momentum_score > 0.05:
            signal = "MODERATE"
        elif momentum_score > -0.05:
            signal = "WEAK"
        else:
            signal = "NEGATIVE"

        direction = "SUPPORTS" if momentum_score > 0.05 else "CONTRADICTS" if momentum_score < -0.05 else "NEUTRAL"

        # Rank within portfolio if provided
        rank = None
        total = None
        portfolio_tickers = kwargs.get("portfolio_tickers", [])
        if portfolio_tickers and len(portfolio_tickers) > 1:
            scores = {}
            for t in portfolio_tickers:
                if t == ticker:
                    scores[t] = momentum_score
                else:
                    try:
                        t_hist = yf.Ticker(t).history(
                            start=(pd.Timestamp(date) - pd.DateOffset(months=13)).strftime("%Y-%m-%d"),
                            end=(pd.Timestamp(date) + pd.DateOffset(days=1)).strftime("%Y-%m-%d"),
                        )
                        if len(t_hist) >= 22:
                            tc = t_hist["Close"]
                            r12 = (tc.iloc[-1] / tc.iloc[-min(252, len(tc))]) - 1 if len(tc) >= 22 else 0
                            r1 = (tc.iloc[-1] / tc.iloc[-min(22, len(tc))]) - 1
                            scores[t] = r12 - r1
                    except Exception:
                        pass
            if scores:
                ranked = sorted(scores, key=lambda k: scores[k], reverse=True)
                rank = ranked.index(ticker) + 1 if ticker in ranked else None
                total = len(ranked)

        rank_label = f" (rank {rank}/{total})" if rank and total else ""
        value_label = f"{momentum_score:+.1%}{rank_label}"
        if reversal_risk:
            value_label += " ⚠️ reversal risk"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(momentum_score, 4),
            value_label=value_label,
            direction=direction,
            detail={
                "ret_12m": round(ret_12m, 4),
                "ret_1m": round(ret_1m, 4),
                "momentum_score": round(momentum_score, 4),
                "reversal_risk": bool(reversal_risk),
                "rank": rank,
                "total": total,
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (insufficient data)",
            direction="NEUTRAL", detail={},
        )
