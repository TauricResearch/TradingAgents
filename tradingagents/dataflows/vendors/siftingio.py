"""Optional US-equity daily OHLCV from SiftingIO, returned as as-traded CSV.

This vendor does not provide split/dividend adjustments or replace the
indicators, fundamentals, or news vendors. No API key is sent until selected.
"""

import csv
import io
import math
import os
import re
from datetime import UTC, date, datetime

import requests

from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)

API_BASE = "https://api.sifting.io"
MAX_PAGES = 100
MAX_STALE_DAYS = 10


def _request(symbol: str, params: dict, key: str) -> dict:
    try:
        response = requests.get(
            f"{API_BASE}/v1/hist/stocks/{symbol}/bars",
            params=params,
            headers={"X-API-Key": key, "Accept-Encoding": "gzip"},
            timeout=30,
            allow_redirects=False,
        )
    except requests.RequestException:
        # Never include request objects, response bodies or credentials in an
        # error: the router passes vendor errors into the model's context.
        raise VendorUnavailableError("SiftingIO request failed") from None
    try:
        if response.status_code in (401, 403):
            raise VendorNotConfiguredError(
                "SiftingIO: check SIFTINGIO_API_KEY and US-stock historical access"
            )
        if response.status_code == 404:
            raise NoMarketDataError(symbol, detail="not covered by SiftingIO stock history")
        if response.status_code != 200:
            raise VendorUnavailableError(f"SiftingIO returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise VendorUnavailableError("SiftingIO returned invalid JSON") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise VendorUnavailableError("SiftingIO returned an invalid bars envelope")
        return payload
    finally:
        response.close()


def _bar_row(bar: dict) -> tuple:
    """Reject malformed rows rather than fabricate missing prices or volume."""
    try:
        timestamp = bar["t"]
        values = tuple(bar[field] for field in ("o", "h", "l", "c", "v"))
        if type(timestamp) is not int or timestamp % 86_400_000:
            raise ValueError("daily UTC bucket required")
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
            raise ValueError("finite numbers required")
        opening, high, low, close, volume = values
        if min(opening, high, low, close) <= 0 or volume < 0:
            raise ValueError("invalid price or volume")
        if not low <= min(opening, close) <= max(opening, close) <= high:
            raise ValueError("invalid OHLC bounds")
        day = datetime.fromtimestamp(timestamp / 1000, tz=UTC).date()
        return (day, *values)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        raise VendorUnavailableError("SiftingIO returned an invalid daily OHLCV bar") from None


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Inclusive YYYY-MM-DD window of daily, regular-session US stock bars.

    Bar timestamps label UTC daily buckets, not session-close timestamps.
    Pagination is bounded; truncated or conflicting results fail explicitly.
    """
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol):
        raise ValueError("SiftingIO requires a US-stock ticker, not a URL or currency pair")
    try:
        if not all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) for value in (start_date, end_date)):
            raise ValueError
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        if start > end:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("Use YYYY-MM-DD dates with start_date <= end_date") from None
    key = os.getenv("SIFTINGIO_API_KEY", "").strip()
    if not key:
        raise VendorNotConfiguredError("SIFTINGIO_API_KEY is not set")

    params = {"start": start_date, "end": end_date, "interval": "1d", "limit": 1000}
    rows, seen_cursors = {}, set()
    for _ in range(MAX_PAGES):
        payload = _request(symbol, params, key)
        metadata = payload.get("meta")
        if not isinstance(metadata, dict):
            raise VendorUnavailableError("SiftingIO returned invalid bars metadata")
        if metadata.get("symbol", symbol) != symbol or metadata.get("interval", "1d") != "1d":
            raise VendorUnavailableError("SiftingIO returned a different symbol or interval")
        for bar in payload["data"]:
            row = _bar_row(bar)
            day = row[0]
            if not start <= day <= end:
                continue  # never leak future bars outside the requested window
            if day in rows and rows[day] != row:
                raise VendorUnavailableError("SiftingIO returned conflicting daily bars")
            rows[day] = row
        cursor = metadata.get("next_cursor")
        if cursor is None or cursor == "":
            break
        if not isinstance(cursor, str) or cursor in seen_cursors:
            raise VendorUnavailableError("SiftingIO returned an invalid or repeated cursor")
        seen_cursors.add(cursor)
        params = {**params, "cursor": cursor}
    else:
        raise VendorUnavailableError("SiftingIO pagination limit reached; narrow the date range")
    if not rows:
        raise NoMarketDataError(symbol, detail="no daily bars in the requested window")
    if (end - max(rows)).days > MAX_STALE_DAYS:
        raise NoMarketDataError(symbol, detail="latest daily bar is stale for the requested end date")

    output = io.StringIO()
    output.write(f"# SiftingIO daily stock data for {symbol}: {start_date} to {end_date}\n")
    output.write("# Regular sessions; as-traded, NOT adjusted for splits or dividends.\n")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("Date", "Open", "High", "Low", "Close", "Volume"))
    writer.writerows(rows[day] for day in sorted(rows))
    return output.getvalue()
