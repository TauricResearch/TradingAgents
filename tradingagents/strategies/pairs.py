"""Pairs Trading strategy signal (§3.8 — Pairs Trading / Statistical Arbitrage).

Cointegration-based spread signal using price ratio z-score vs a correlated peer.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §3.8
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .base import BaseStrategy, StrategySignal
from ._data import get_ohlcv, get_info

logger = logging.getLogger(__name__)

# Simple sector-based peer mapping (one representative peer per sector)
_SECTOR_PEERS: dict[str, str] = {
    "Technology": "MSFT",
    "Healthcare": "JNJ",
    "Financial Services": "JPM",
    "Financials": "JPM",
    "Consumer Cyclical": "AMZN",
    "Consumer Defensive": "PG",
    "Energy": "XOM",
    "Industrials": "HON",
    "Basic Materials": "LIN",
    "Utilities": "NEE",
    "Real Estate": "PLD",
    "Communication Services": "GOOGL",
}


class PairsStrategy(BaseStrategy):
    name = "Pairs Trading (§3.8)"
    roles = ["market", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        info = get_info(ticker, context)
        if not info:
            return None

        sector = info.get("sector", "")
        peer = _SECTOR_PEERS.get(sector)
        if not peer or peer.upper() == ticker.upper():
            return None

        df = get_ohlcv(ticker, date, context)
        peer_df = get_ohlcv(peer, date)
        if df is None or peer_df is None or len(df) < 60 or len(peer_df) < 60:
            return None

        # Price ratio z-score over 60 days
        stock_close = df["Close"].values[-60:]
        peer_close = peer_df["Close"].values[-60:]
        if np.any(peer_close == 0):
            return None

        ratio = stock_close / peer_close
        mean = float(np.mean(ratio))
        std = float(np.std(ratio))
        if std == 0:
            return None

        z = (ratio[-1] - mean) / std
        # High z → stock overvalued vs peer → bearish; low z → bullish
        strength = max(-1.0, min(1.0, -z / 2.5))
        if z > 1.5:
            direction, label = "bearish", "overvalued vs peer"
        elif z < -1.5:
            direction, label = "bullish", "undervalued vs peer"
        else:
            direction, label = "neutral", "fair vs peer"

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=round(strength, 4),
            direction=direction,
            detail=f"{label}: {ticker}/{peer} ratio z={z:+.2f}",
        )
