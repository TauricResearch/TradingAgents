"""Multifactor strategy signal (§3.6 — Multifactor Models).

Combined momentum + value + quality + low-vol composite.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.6
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv, get_info


class MultifactorStrategy(BaseStrategy):
    name = "Multifactor (§3.6)"
    roles = ["researcher", "risk"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        df = get_ohlcv(ticker, date, context)
        info = get_info(ticker, context)
        if df is None or len(df) < 252 or not info:
            return None

        factors: list[float] = []
        details: list[str] = []
        close = df["Close"].values

        # Momentum factor: 12-1 month return
        if len(close) >= 252:
            mom = (close[-21] - close[-252]) / close[-252]
            factors.append(max(-1.0, min(1.0, mom)))
            details.append(f"mom={mom:+.2%}")

        # Value factor: inverse PE
        pe = info.get("trailingPE")
        if pe and pe > 0:
            val = min(1.0 / pe / 0.15, 1.0) * 2 - 1
            factors.append(max(-1.0, min(1.0, val)))
            details.append(f"val_pe={pe:.1f}")

        # Quality factor: ROE
        roe = info.get("returnOnEquity")
        if roe is not None:
            factors.append(max(-1.0, min(1.0, roe * 2)))
            details.append(f"roe={roe:.2%}")

        # Low-vol factor
        if len(close) >= 63:
            vol = float(np.std(np.diff(np.log(close[-63:]))) * np.sqrt(252))
            lv = max(-1.0, min(1.0, (0.30 - vol) / 0.30))
            factors.append(lv)
            details.append(f"vol={vol:.1%}")

        if not factors:
            return None

        strength = round(sum(factors) / len(factors), 4)
        strength = max(-1.0, min(1.0, strength))
        direction = "bullish" if strength > 0.05 else ("bearish" if strength < -0.05 else "neutral")

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=strength,
            direction=direction,
            detail=f"{len(factors)}-factor composite: {', '.join(details)}",
        )
