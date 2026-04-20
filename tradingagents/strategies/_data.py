"""Shared data helpers for strategy modules."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def get_ohlcv(ticker: str, date: str, context: dict[str, Any] | None = None) -> pd.DataFrame | None:
    """Return OHLCV DataFrame up to *date*, or None on failure.

    Uses context["ohlcv"] if provided, otherwise fetches via load_ohlcv.
    """
    if context and "ohlcv" in context:
        return context["ohlcv"]
    try:
        from tradingagents.dataflows.stockstats_utils import load_ohlcv
        df = load_ohlcv(ticker, date)
        return df if not df.empty else None
    except Exception:
        logger.debug("Failed to load OHLCV for %s@%s", ticker, date, exc_info=True)
        return None


def get_info(ticker: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return yfinance .info dict, or None on failure."""
    if context and "info" in context:
        return context["info"]
    try:
        import yfinance as yf
        from tradingagents.dataflows.stockstats_utils import yf_retry
        return yf_retry(lambda: yf.Ticker(ticker.upper()).info) or None
    except Exception:
        logger.debug("Failed to load info for %s", ticker, exc_info=True)
        return None
