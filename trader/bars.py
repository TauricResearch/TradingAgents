"""Whether Yahoo has published a trade date's daily candle (#53).

Yahoo drops the day just ended from its daily series shortly after 00:00 UTC and
gives it back hours later (on 2026-11-14, between 06:50 and 07:20 UTC), so the
research at 00:05 sees the candles up to the day before its trade date only.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)


def published(symbol: str, trade_date: str) -> bool:
    """Whether Yahoo's daily series of ``symbol`` has a candle dated ``trade_date``.
    False as well when Yahoo could not be asked: the coin is then researched again
    once it can be, which costs a run, not a wrong rating."""
    day = date.fromisoformat(trade_date)
    try:
        frame = yf.Ticker(symbol).history(
            start=day - timedelta(days=3), end=day + timedelta(days=2), interval="1d", auto_adjust=False,
        )
    except Exception as exc:
        logger.warning("could not ask Yahoo for the daily candles of %s: %s", symbol, type(exc).__name__)
        return False
    return any(stamp.date() == day for stamp in frame.index)
