"""Moving Average Crossover strategy signal (§3.11-3.13).

Detects SMA 50/200 crossovers (golden cross / death cross) and current
trend position. Golden cross (SMA50 crosses above SMA200) is bullish;
death cross (SMA50 crosses below SMA200) is bearish.

Reference: Kakushadze & Serur §3.11-3.13 — "Moving Average Crossover"
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal

_SMA_SHORT = 50
_SMA_LONG = 200


class MovingAverageStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Golden/death cross is a lagging but reliable trend confirmation. Tips: Many false signals in choppy markets — require volume confirmation. SMA50 > SMA200 is bullish structure. Best used to confirm other signals, not as standalone entry."

    name = "moving_average"
    description = "SMA 50/200 crossover, golden/death cross detection"
    target_analysts = ["technical"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        hist = kwargs.get("hist")
        if hist is None:
            end = pd.Timestamp(date)
            start = end - pd.DateOffset(days=400)  # ~200 trading days + buffer
            hist = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=(end + pd.DateOffset(days=1)).strftime("%Y-%m-%d"),
            )

        if hist.empty or len(hist) < _SMA_LONG:
            return self._neutral(ticker, date)

        close = hist["Close"]
        sma_short = close.rolling(_SMA_SHORT).mean()
        sma_long = close.rolling(_SMA_LONG).mean()

        # Drop NaN rows (need at least SMA_LONG valid values)
        valid = sma_long.dropna()
        if len(valid) < 2:
            return self._neutral(ticker, date)

        current_price = float(close.iloc[-1])
        sma50 = float(sma_short.iloc[-1])
        sma200 = float(sma_long.iloc[-1])

        # Detect crossover: compare sign of (SMA50 - SMA200) today vs yesterday
        diff = sma_short - sma_long
        diff_valid = diff.dropna()
        if len(diff_valid) < 2:
            return self._neutral(ticker, date)

        # Find most recent crossover
        signs = (diff_valid > 0).astype(int)
        crossovers = signs.diff().dropna()
        cross_dates = crossovers[crossovers != 0]

        cross_type = None
        days_since_cross = None
        if not cross_dates.empty:
            last_cross_date = cross_dates.index[-1]
            last_cross_val = int(cross_dates.iloc[-1])
            cross_type = "golden" if last_cross_val > 0 else "death"
            days_since_cross = (close.index[-1] - last_cross_date).days

        # Current trend: price vs SMAs
        above_50 = current_price > sma50
        above_200 = current_price > sma200
        bullish_alignment = sma50 > sma200  # SMA50 above SMA200

        # Signal classification
        if bullish_alignment and above_50 and above_200:
            signal = "STRONG"
            direction = "SUPPORTS"
        elif bullish_alignment:
            signal = "MODERATE"
            direction = "SUPPORTS"
        elif not bullish_alignment and not above_50 and not above_200:
            signal = "STRONG"
            direction = "CONTRADICTS"
        elif not bullish_alignment:
            signal = "MODERATE"
            direction = "CONTRADICTS"
        else:
            signal = "NEUTRAL"
            direction = "NEUTRAL"

        # Recent cross overrides signal strength
        if cross_type and days_since_cross is not None and days_since_cross <= 30:
            signal = "STRONG"
            direction = "SUPPORTS" if cross_type == "golden" else "CONTRADICTS"

        # Value label
        parts = []
        if cross_type and days_since_cross is not None:
            cross_label = "Golden Cross" if cross_type == "golden" else "Death Cross"
            parts.append(f"{cross_label} {days_since_cross}d ago")
        trend = "bullish" if bullish_alignment else "bearish"
        parts.append(f"trend={trend}")
        pct_above_200 = ((current_price / sma200) - 1) * 100
        parts.append(f"price {pct_above_200:+.1f}% vs SMA200")
        value_label = ", ".join(parts)

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(pct_above_200 / 100, 4),
            value_label=value_label,
            direction=direction,
            detail={
                "sma50": round(sma50, 2),
                "sma200": round(sma200, 2),
                "current_price": round(current_price, 2),
                "above_sma50": above_50,
                "above_sma200": above_200,
                "bullish_alignment": bullish_alignment,
                "cross_type": cross_type,
                "days_since_cross": days_since_cross,
                "pct_above_sma200": round(pct_above_200, 2),
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (insufficient data)",
            direction="NEUTRAL", detail={},
        )
