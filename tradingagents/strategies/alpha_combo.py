"""Alpha Combos strategy signal (§3.20).

Weighted meta-signal combining all Tier 1 strategy signals into a single
composite alpha score. Each Tier 1 signal's normalized value is weighted
and summed. Weights are fixed (equal-weight baseline) but can be adjusted
based on strategy scorecard tracking over time.

Unlike multifactor.py (which computes its own factors from raw data),
alpha_combo operates on already-computed strategy signals — it's a
second-pass aggregation.

Reference: Kakushadze & Serur §3.20 — "Alpha Combos"
"""

from __future__ import annotations

import numpy as np

from tradingagents.strategies.base import BaseStrategy, StrategySignal

# Tier 1 strategy names and their normalization ranges
# value_range: (min_typical, max_typical) used to normalize to [-1, 1]
TIER1_CONFIG: dict[str, dict] = {
    "momentum":          {"weight": 0.20, "range": (-0.30, 0.30)},
    "earnings_momentum": {"weight": 0.10, "range": (-3.0, 3.0)},
    "value":             {"weight": 0.15, "range": (0.0, 1.0)},
    "volatility":        {"weight": 0.10, "range": (0.10, 0.60)},
    "multifactor":       {"weight": 0.15, "range": (-1.0, 1.0)},
    "mean_reversion":    {"weight": 0.10, "range": (-3.0, 3.0)},
    "moving_average":    {"weight": 0.10, "range": (-1.0, 1.0)},
    "sector_rotation":   {"weight": 0.10, "range": (-0.30, 0.30)},
}

# Direction mapping: how each signal's direction maps to bullish/bearish
# 1 = SUPPORTS is bullish, -1 = SUPPORTS is bearish (inverted signals like vol)
DIRECTION_SIGN: dict[str, int] = {
    "momentum": 1,
    "earnings_momentum": 1,
    "value": 1,           # high value score = cheap = bullish
    "volatility": -1,     # high vol = bearish (low-vol anomaly)
    "multifactor": 1,
    "mean_reversion": -1, # high z-score = overbought = bearish
    "moving_average": 1,
    "sector_rotation": 1,
}


def _normalize(value: float, lo: float, hi: float) -> float:
    """Normalize value to [-1, 1] range given typical bounds."""
    if hi == lo:
        return 0.0
    mid = (hi + lo) / 2
    half = (hi - lo) / 2
    return float(np.clip((value - mid) / half, -1, 1))


class AlphaComboStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Ensemble of top-performing factor signals — diversified alpha source. Tips: Interpret as 'weight of evidence' — more factors agreeing = higher confidence. Individual factor weights shift over time. Strongest when combined with macro regime awareness."

    name = "alpha_combo"
    description = "Weighted meta-signal combining all Tier 1 strategy signals"
    target_analysts = ["portfolio"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        """Combine Tier 1 signals into a single alpha score.

        kwargs:
            tier1_signals: list[StrategySignal] — pre-computed Tier 1 signals
        """
        tier1: list[StrategySignal] = kwargs.get("tier1_signals", [])
        if not tier1:
            return self._neutral(ticker, date)

        # Index signals by name
        by_name = {s["name"]: s for s in tier1 if s.get("name")}

        weighted_sum = 0.0
        total_weight = 0.0
        contributions: dict[str, float] = {}

        for name, cfg in TIER1_CONFIG.items():
            sig = by_name.get(name)
            if not sig or sig.get("signal") == "NEUTRAL":
                continue

            value = sig.get("value", 0.0)
            lo, hi = cfg["range"]
            normed = _normalize(value, lo, hi)

            # Apply direction sign (e.g., high vol is bearish)
            sign = DIRECTION_SIGN.get(name, 1)
            normed *= sign

            w = cfg["weight"]
            weighted_sum += normed * w
            total_weight += w
            contributions[name] = round(normed * w, 4)

        if total_weight == 0:
            return self._neutral(ticker, date)

        # Normalize by total weight used (handles missing signals)
        alpha = weighted_sum / total_weight

        # Classify
        if alpha > 0.3:
            signal = "STRONG"
        elif alpha > 0.1:
            signal = "MODERATE"
        elif alpha > -0.1:
            signal = "NEUTRAL"
        elif alpha > -0.3:
            signal = "WEAK"
        else:
            signal = "NEGATIVE"

        direction = "SUPPORTS" if alpha > 0.1 else "CONTRADICTS" if alpha < -0.1 else "NEUTRAL"

        # Top contributors
        sorted_contrib = sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)
        top = [f"{n}={v:+.3f}" for n, v in sorted_contrib[:3]]
        n_signals = len(contributions)

        value_label = f"{alpha:+.3f} ({signal.lower()}, {n_signals}/{len(TIER1_CONFIG)} signals) [{', '.join(top)}]"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(alpha, 4),
            value_label=value_label,
            direction=direction,
            detail={
                "alpha": round(alpha, 4),
                "contributions": contributions,
                "n_signals": n_signals,
                "total_weight": round(total_weight, 4),
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0,
            value_label="N/A (no Tier 1 signals available)",
            direction="NEUTRAL", detail={},
        )
