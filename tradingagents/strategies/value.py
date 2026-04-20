"""Value strategy signal (§3.3 — Value).

Composite value score from Book/Market, Earnings/Price, and CashFlow/Price.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.3
"""

from __future__ import annotations

from typing import Any

from .base import BaseStrategy, StrategySignal
from ._data import get_info


class ValueStrategy(BaseStrategy):
    name = "Value (§3.3)"
    roles = ["fundamentals", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        info = get_info(ticker, context)
        if not info:
            return None

        scores: list[float] = []

        # Book/Market (inverse of P/B)
        pb = info.get("priceToBook")
        if pb and pb > 0:
            bm = 1.0 / pb
            scores.append(min(bm, 3.0) / 3.0)  # normalize: BM=3 → 1.0

        # Earnings/Price (inverse of trailing PE)
        pe = info.get("trailingPE")
        if pe and pe > 0:
            ep = 1.0 / pe
            scores.append(min(ep, 0.15) / 0.15)

        # Free Cash Flow yield proxy
        mcap = info.get("marketCap")
        fcf = info.get("freeCashflow")
        if mcap and fcf and mcap > 0:
            cfy = fcf / mcap
            scores.append(max(-1.0, min(cfy / 0.10, 1.0)))

        if not scores:
            return None

        composite = sum(scores) / len(scores)
        # Map [0,1] → [-1,1]: high value = bullish
        strength = max(-1.0, min(1.0, composite * 2 - 1))
        direction = "bullish" if strength > 0.1 else ("bearish" if strength < -0.1 else "neutral")

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"Composite value score: {composite:.2f} from {len(scores)} factors",
        )
