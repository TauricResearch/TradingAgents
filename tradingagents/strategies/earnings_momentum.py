"""Earnings Momentum strategy signal (§3.2).

Standardized Unexpected Earnings (SUE) from earnings surprise magnitude.
Post-earnings drift: stocks with large positive surprises tend to continue
outperforming, and vice versa.

SUE = (Actual EPS - Estimate EPS) / σ(earnings surprises)

Reference: Kakushadze & Serur §3.2 — "Earnings Momentum"
"""

from __future__ import annotations

import numpy as np
import yfinance as yf
import pandas as pd

from tradingagents.strategies.base import BaseStrategy, StrategySignal


class EarningsMomentumStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Most reliable within 30 days post-earnings — signal decays quickly. Tips: Combine with price momentum for 'earnings + price' confirmation. Beware one-time items inflating surprise. Strongest for growth stocks where expectations are high."

    name = "earnings_momentum"
    description = "SUE (Standardized Unexpected Earnings) from earnings surprise"
    target_analysts = ["fundamentals"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        try:
            ed = yf.Ticker(ticker).earnings_dates
        except Exception:
            return self._neutral(ticker, date)

        if ed is None or ed.empty:
            return self._neutral(ticker, date)

        # Filter to reported earnings on or before analysis date
        cutoff = pd.Timestamp(date, tz="UTC") if ed.index.tz else pd.Timestamp(date)
        reported = ed[ed.index <= cutoff].dropna(subset=["Reported EPS", "EPS Estimate"])
        if reported.empty:
            return self._neutral(ticker, date)

        # Compute raw surprises (actual - estimate)
        reported = reported.copy()
        reported["surprise"] = reported["Reported EPS"] - reported["EPS Estimate"]

        # SUE: standardize by σ of surprises (need ≥2 quarters)
        surprises = reported["surprise"].values
        latest_surprise = float(surprises[0])  # most recent first
        latest_pct = float(reported["Surprise(%)"].iloc[0]) if "Surprise(%)" in reported.columns and pd.notna(reported["Surprise(%)"].iloc[0]) else 0.0

        if len(surprises) >= 2:
            std = float(np.std(surprises, ddof=1))
            sue = latest_surprise / std if std > 0 else 0.0
        else:
            sue = 0.0

        # Streak: consecutive positive or negative surprises
        streak = 0
        for s in surprises:
            if (s > 0 and streak >= 0) or (s < 0 and streak <= 0):
                streak += 1 if s > 0 else -1
            else:
                break

        # Signal strength based on SUE magnitude
        abs_sue = abs(sue)
        if abs_sue > 2.0:
            signal = "STRONG" if sue > 0 else "NEGATIVE"
        elif abs_sue > 1.0:
            signal = "MODERATE" if sue > 0 else "WEAK"
        else:
            signal = "NEUTRAL"

        direction = "SUPPORTS" if sue > 1.0 else "CONTRADICTS" if sue < -1.0 else "NEUTRAL"

        streak_label = f", {abs(streak)}Q {'beat' if streak > 0 else 'miss'} streak" if abs(streak) >= 2 else ""
        value_label = f"SUE={sue:+.2f} (last surprise: {latest_pct:+.1f}%{streak_label})"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(sue, 4),
            value_label=value_label,
            direction=direction,
            detail={
                "sue": round(sue, 4),
                "latest_surprise": round(latest_surprise, 4),
                "latest_surprise_pct": round(latest_pct, 2),
                "streak": streak,
                "n_quarters": len(surprises),
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (no earnings data)",
            direction="NEUTRAL", detail={},
        )
