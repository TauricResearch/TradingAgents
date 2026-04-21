"""Sector Rotation strategy signal (§4.1 — Sector Rotation).

Compares ticker's sector performance to broad market using relative strength.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §4.1
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv, get_info

logger = logging.getLogger(__name__)

# Sector ETF proxies
_SECTOR_ETFS: dict[str, str] = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Financials": "XLF",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}


class SectorRotationStrategy(BaseStrategy):
    name = "Sector Rotation (§4.1)"
    roles = ["market", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        info = get_info(ticker, context)
        if not info:
            return None

        sector = info.get("sector", "")
        etf = _SECTOR_ETFS.get(sector)
        if not etf:
            return None

        sector_df = get_ohlcv(etf, date)
        spy_df = get_ohlcv("SPY", date)
        if sector_df is None or spy_df is None or len(sector_df) < 63 or len(spy_df) < 63:
            return None

        # 3-month relative strength: sector ETF vs SPY
        sec_ret = (sector_df["Close"].values[-1] - sector_df["Close"].values[-63]) / sector_df["Close"].values[-63]
        spy_ret = (spy_df["Close"].values[-1] - spy_df["Close"].values[-63]) / spy_df["Close"].values[-63]
        rel = sec_ret - spy_ret

        strength = max(-1.0, min(1.0, rel * 5))
        direction = "bullish" if strength > 0.1 else ("bearish" if strength < -0.1 else "neutral")

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"{sector} ({etf}) 63d relative strength vs SPY: {rel:+.2%}",
        )
