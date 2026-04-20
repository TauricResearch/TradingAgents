"""Support & Resistance strategy signal (§3.14).

Detects local min/max price levels from trailing 6-month daily data.
Identifies nearest support (below current price) and resistance (above)
for alert thresholds and entry/exit timing.

Reference: Kakushadze & Serur §3.14 — "Support and Resistance"
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from tradingagents.strategies.base import BaseStrategy, StrategySignal

_LOOKBACK_DAYS = 180  # ~6 months of calendar days
_ORDER = 5  # local extrema window: point must be min/max within ±ORDER bars


def _find_local_extrema(close: pd.Series, order: int = _ORDER) -> tuple[list[float], list[float]]:
    """Find local minima (supports) and maxima (resistances) in price series."""
    supports: list[float] = []
    resistances: list[float] = []
    values = close.values

    for i in range(order, len(values) - order):
        window = values[i - order : i + order + 1]
        if values[i] == window.min():
            supports.append(float(values[i]))
        elif values[i] == window.max():
            resistances.append(float(values[i]))

    return supports, resistances


def _cluster_levels(levels: list[float], tolerance: float = 0.02) -> list[float]:
    """Cluster nearby price levels (within tolerance %) into single levels."""
    if not levels:
        return []
    sorted_levels = sorted(levels)
    clusters: list[list[float]] = [[sorted_levels[0]]]
    for lvl in sorted_levels[1:]:
        if (lvl - clusters[-1][-1]) / clusters[-1][-1] <= tolerance:
            clusters[-1].append(lvl)
        else:
            clusters.append([lvl])
    return [round(np.mean(c), 2) for c in clusters]


class SupportResistanceStrategy(BaseStrategy):

    @property
    def interpretation_guide(self) -> str:
        return "Usage: Key levels for stop-loss placement and entry timing. Tips: Levels are approximate — use zones not exact prices. Breaks of major support on high volume are significant. Combine with RSI for 'oversold at support' high-conviction entries."

    name = "support_resistance"
    description = "Local min/max price levels for support/resistance"
    target_analysts = ["technical"]

    def compute(self, ticker: str, date: str, **kwargs) -> StrategySignal:
        hist = kwargs.get("hist")
        if hist is None:
            end = pd.Timestamp(date)
            start = end - pd.DateOffset(days=_LOOKBACK_DAYS)
            hist = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=(end + pd.DateOffset(days=1)).strftime("%Y-%m-%d"),
            )

        if hist.empty or len(hist) < _ORDER * 3:
            return self._neutral(ticker, date)

        close = hist["Close"]
        current = float(close.iloc[-1])

        raw_supports, raw_resistances = _find_local_extrema(close)
        supports = _cluster_levels(raw_supports)
        resistances = _cluster_levels(raw_resistances)

        # Nearest support below current price
        below = [s for s in supports if s < current]
        nearest_support = max(below) if below else None

        # Nearest resistance above current price
        above = [r for r in resistances if r > current]
        nearest_resistance = min(above) if above else None

        # Distance to nearest levels (as % of current price)
        support_dist = ((current - nearest_support) / current * 100) if nearest_support else None
        resist_dist = ((nearest_resistance - current) / current * 100) if nearest_resistance else None

        # Signal: near support = bullish (SUPPORTS), near resistance = bearish (CONTRADICTS)
        if support_dist is not None and support_dist < 3:
            signal, direction = "STRONG", "SUPPORTS"
            label = f"near support ${nearest_support:.2f} ({support_dist:.1f}% below)"
        elif resist_dist is not None and resist_dist < 3:
            signal, direction = "STRONG", "CONTRADICTS"
            label = f"near resistance ${nearest_resistance:.2f} ({resist_dist:.1f}% above)"
        elif support_dist is not None and support_dist < 8:
            signal, direction = "MODERATE", "SUPPORTS"
            label = f"support ${nearest_support:.2f} ({support_dist:.1f}% below)"
        elif resist_dist is not None and resist_dist < 8:
            signal, direction = "MODERATE", "CONTRADICTS"
            label = f"resistance ${nearest_resistance:.2f} ({resist_dist:.1f}% above)"
        else:
            signal, direction = "NEUTRAL", "NEUTRAL"
            parts = []
            if nearest_support:
                parts.append(f"S=${nearest_support:.2f}")
            if nearest_resistance:
                parts.append(f"R=${nearest_resistance:.2f}")
            label = ", ".join(parts) if parts else "no clear levels"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal=signal,
            value=round(support_dist or 0, 4),
            value_label=label,
            direction=direction,
            detail={
                "current_price": round(current, 2),
                "nearest_support": nearest_support,
                "nearest_resistance": nearest_resistance,
                "support_distance_pct": round(support_dist, 2) if support_dist else None,
                "resistance_distance_pct": round(resist_dist, 2) if resist_dist else None,
                "all_supports": supports[-5:],  # last 5
                "all_resistances": resistances[-5:],
            },
        )

    def _neutral(self, ticker: str, date: str) -> StrategySignal:
        return StrategySignal(
            name=self.name, ticker=ticker, date=date,
            signal="NEUTRAL", value=0.0, value_label="N/A (insufficient data)",
            direction="NEUTRAL", detail={},
        )
