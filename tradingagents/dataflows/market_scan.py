"""Daily market-data snapshots for a user-supplied watchlist."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component
from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv


@dataclass(frozen=True)
class MarketScanResult:
    requested_symbol: str
    symbol: str
    latest_date: str
    close: float
    change_percent: float | None
    volume: int | None


def scan_market_data(symbol: str, as_of_date: str) -> MarketScanResult:
    """Return the latest verified daily close and change for one symbol."""
    canonical = normalize_symbol(symbol)
    safe_ticker_component(canonical)
    data = load_ohlcv(symbol, as_of_date, fill_gaps=False)
    if data is None or data.empty or "Date" not in data or "Close" not in data:
        raise NoMarketDataError(symbol, canonical, "no usable daily OHLCV rows")

    frame = data.copy()
    dates = pd.to_datetime(frame["Date"], errors="coerce")
    if dates.dt.tz is not None:
        dates = dates.dt.tz_localize(None)
    frame["Date"] = dates
    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    frame = frame.dropna(subset=["Date", "Close"])
    frame = frame[frame["Close"].map(math.isfinite)]
    frame = frame[frame["Date"] <= pd.Timestamp(as_of_date)].sort_values("Date")
    if frame.empty:
        raise NoMarketDataError(
            symbol, canonical, "no usable daily close on or before the requested date"
        )

    latest = frame.iloc[-1]
    close = float(latest["Close"])
    change_percent = None
    if len(frame) > 1:
        previous_close = float(frame.iloc[-2]["Close"])
        if previous_close != 0:
            change_percent = (close - previous_close) / previous_close * 100

    volume = None
    if "Volume" in frame:
        latest_volume = pd.to_numeric(latest["Volume"], errors="coerce")
        if pd.notna(latest_volume):
            volume = int(latest_volume)

    return MarketScanResult(
        requested_symbol=symbol,
        symbol=canonical,
        latest_date=latest["Date"].date().isoformat(),
        close=close,
        change_percent=change_percent,
        volume=volume,
    )
