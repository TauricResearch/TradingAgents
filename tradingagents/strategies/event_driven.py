"""Event-Driven M&A activity detection (§3.16).

Detects potential M&A activity from price/volume patterns:
- Abnormal volume spikes (>2σ above 20-day mean)
- Gap-ups/downs on high volume (potential bid/offer)
- Compressed volatility post-spike (merger arb convergence)
- Price clustering near round numbers (typical of bid prices)

Reference: Kakushadze & Serur §3.16 — "Merger Arbitrage"
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal


class EventDrivenStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Flags upcoming catalysts (earnings, dividends, ex-dates). Tips: Position sizing should increase near catalysts. Post-event drift is real — momentum continues 1-3 days after earnings. Combine with IV signal for event risk assessment."

    name = "event_driven"
    description = "M&A activity detection from price/volume patterns"
    target_analysts = ["news", "research"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        hist = kwargs.get("hist")
        if hist is None:
            end = pd.Timestamp(date)
            start = end - pd.DateOffset(days=90)
            hist = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=(end + pd.DateOffset(days=1)).strftime("%Y-%m-%d"),
            )
        if hist.empty or len(hist) < 30:
            return self._neutral(ticker, date)

        close = hist["Close"].values
        volume = hist["Volume"].values.astype(float)

        # --- Volume spike detection (last 5 days vs 20-day trailing) ---
        vol_20 = np.mean(volume[-25:-5]) if len(volume) >= 25 else np.mean(volume[:-5])
        vol_std = np.std(volume[-25:-5]) if len(volume) >= 25 else np.std(volume[:-5])
        recent_vol = np.mean(volume[-5:])
        vol_z = float((recent_vol - vol_20) / vol_std) if vol_std > 0 else 0.0

        # --- Gap detection (largest single-day gap in last 20 days) ---
        daily_gaps = np.abs(np.diff(close[-21:])) / close[-21:-1] if len(close) >= 21 else np.array([0.0])
        max_gap = float(np.max(daily_gaps)) if len(daily_gaps) > 0 else 0.0

        # --- Post-event volatility compression ---
        # Compare last 5-day vol to prior 20-day vol
        returns = np.diff(close) / close[:-1]
        if len(returns) >= 25:
            recent_std = float(np.std(returns[-5:]))
            prior_std = float(np.std(returns[-25:-5]))
            vol_compression = prior_std / recent_std if recent_std > 0 else 1.0
        else:
            vol_compression = 1.0

        # --- Price clustering near round number (bid price pattern) ---
        current = float(close[-1])
        nearest_round = round(current / 5) * 5  # nearest $5 increment
        round_proximity = abs(current - nearest_round) / current if current > 0 else 1.0

        # --- Composite M&A score ---
        score = 0.0
        flags: list[str] = []

        if vol_z > 2.0:
            score += 0.3
            flags.append(f"volume spike {vol_z:.1f}σ")
        if max_gap > 0.05:
            score += 0.3
            flags.append(f"gap {max_gap:.1%}")
        if vol_compression > 2.0:
            score += 0.2
            flags.append(f"vol compressed {vol_compression:.1f}x")
        if round_proximity < 0.02:
            score += 0.2
            flags.append(f"near ${nearest_round:.0f}")

        # Interpret
        if score >= 0.6:
            signal, direction = "STRONG", "SUPPORTS"
            label = f"M&A signals detected ({', '.join(flags)})"
        elif score >= 0.3:
            signal, direction = "MODERATE", "NEUTRAL"
            label = f"Possible event activity ({', '.join(flags)})"
        else:
            signal, direction = "NEUTRAL", "NEUTRAL"
            label = "No M&A pattern detected"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(score, 4),
            value_label=label,
            direction=direction,
            detail={
                "volume_z": round(vol_z, 4),
                "max_gap_pct": round(max_gap, 4),
                "vol_compression": round(vol_compression, 4),
                "round_proximity": round(round_proximity, 4),
                "nearest_round": nearest_round,
                "flags": flags,
                "composite_score": round(score, 4),
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0,
            value_label="Insufficient data for M&A detection",
            direction="NEUTRAL", detail={},
        )
