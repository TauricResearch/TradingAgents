"""Finnhub stock price data functions.

Provides OHLCV candle data and real-time quotes using the Finnhub REST API.
Output formats mirror the Alpha Vantage equivalents so LLM agents receive
consistent data regardless of the active vendor.
"""

from datetime import datetime

import pandas as pd

from .finnhub_common import (
    FinnhubError,
    ThirdPartyParseError,
    _make_api_request,
    _now_str,
    _to_unix_timestamp,
)


# Finnhub resolution codes for the /stock/candle endpoint
_RESOLUTION_DAILY = "D"


def get_stock_candles(symbol: str, start_date: str, end_date: str) -> str:
    """Fetch daily OHLCV data for a symbol via Finnhub /stock/candle.

    Returns a CSV-formatted string with columns matching the Alpha Vantage
    TIME_SERIES_DAILY_ADJUSTED output (Date, Open, High, Low, Close, Volume)
    so that downstream agents see a consistent format regardless of vendor.

    Args:
        symbol: Equity ticker symbol (e.g. "AAPL").
        start_date: Inclusive start date in YYYY-MM-DD format.
        end_date: Inclusive end date in YYYY-MM-DD format.

    Returns:
        CSV string with header row: ``timestamp,open,high,low,close,volume``

    Raises:
        FinnhubError: On API-level errors or when the symbol returns no data.
        ThirdPartyParseError: When the response cannot be interpreted.
    """
    params = {
        "symbol": symbol,
        "resolution": _RESOLUTION_DAILY,
        "from": _to_unix_timestamp(start_date),
        "to": _to_unix_timestamp(end_date) + 86400,  # include end date (end of day)
    }

    data = _make_api_request("stock/candle", params)

    status = data.get("s")
    if status == "no_data":
        raise FinnhubError(
            f"No candle data returned for symbol={symbol}, "
            f"start={start_date}, end={end_date}"
        )
    if status != "ok":
        raise FinnhubError(
            f"Unexpected candle response status '{status}' for symbol={symbol}"
        )

    # Finnhub returns parallel lists: t (timestamps), o, h, l, c, v
    timestamps: list[int] = data.get("t", [])
    opens: list[float] = data.get("o", [])
    highs: list[float] = data.get("h", [])
    lows: list[float] = data.get("l", [])
    closes: list[float] = data.get("c", [])
    volumes: list[int] = data.get("v", [])

    if not timestamps:
        raise FinnhubError(
            f"Empty candle data for symbol={symbol}, "
            f"start={start_date}, end={end_date}"
        )

    rows: list[str] = ["timestamp,open,high,low,close,volume"]
    for ts, o, h, lo, c, v in zip(timestamps, opens, highs, lows, closes, volumes):
        date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        rows.append(f"{date_str},{o},{h},{lo},{c},{v}")

    return "\n".join(rows)


def get_quote(symbol: str) -> dict:
    """Fetch the latest real-time quote for a symbol via Finnhub /quote.

    Returns a normalised dict with human-readable keys so callers do not need
    to map Finnhub's single-letter field names.

    Args:
        symbol: Equity ticker symbol (e.g. "AAPL").

    Returns:
        Dict with keys:
            - ``symbol`` (str)
            - ``current_price`` (float)
            - ``change`` (float): Absolute change from previous close.
            - ``change_percent`` (float): Percentage change from previous close.
            - ``high`` (float): Day high.
            - ``low`` (float): Day low.
            - ``open`` (float): Day open.
            - ``prev_close`` (float): Previous close price.
            - ``timestamp`` (str): ISO datetime of the quote.

    Raises:
        FinnhubError: When the API returns an error or the symbol is invalid.
        ThirdPartyParseError: When the response cannot be parsed.
    """
    data = _make_api_request("quote", {"symbol": symbol})

    current_price: float = data.get("c", 0.0)
    prev_close: float = data.get("pc", 0.0)

    # Finnhub returns d (change) and dp (change percent) directly
    change: float = data.get("d", 0.0)
    change_percent: float = data.get("dp", 0.0)

    # Validate that we received a real quote (current_price == 0 means unknown symbol)
    if current_price == 0 and prev_close == 0:
        raise FinnhubError(
            f"Quote returned all-zero values for symbol={symbol}. "
            "Symbol may be invalid or market data unavailable."
        )

    timestamp_unix: int = data.get("t", 0)
    if timestamp_unix:
        timestamp_str = datetime.fromtimestamp(timestamp_unix).strftime("%Y-%m-%d %H:%M:%S")
    else:
        timestamp_str = _now_str()

    return {
        "symbol": symbol,
        "current_price": current_price,
        "change": change,
        "change_percent": change_percent,
        "high": data.get("h", 0.0),
        "low": data.get("l", 0.0),
        "open": data.get("o", 0.0),
        "prev_close": prev_close,
        "timestamp": timestamp_str,
    }
