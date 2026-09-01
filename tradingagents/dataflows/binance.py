"""Binance vendor: native OHLCV market data for crypto assets.

Binance's public klines endpoint requires no API key. Symbol resolution
mirrors symbol_utils.crypto_base(): a user-facing symbol like BTC-USD or
BTCUSD resolves to Binance's USDT-quoted pair (BTCUSDT), matching the
project's existing "-USD -> USDT" convention for exchanges that don't
quote directly against fiat.

Unlike yfinance (which returns full daily history in a single call with
no row cap), Binance's REST klines endpoint caps each request at 1000
candles (~2.7 years of daily bars). Requests spanning more than 1000 days
are paginated: each batch's last candle timestamp seeds the next batch's
startTime, until the requested range is fully covered.
"""

from datetime import datetime, timezone

import pandas as pd
import requests

from .errors import NoMarketDataError
from .symbol_utils import crypto_base

_BASE_URL = "https://api.binance.com/api/v3/klines"
_MAX_LIMIT = 1000  # Binance hard cap per request


def _to_binance_symbol(symbol: str) -> str | None:
    """Resolve a user symbol (BTC-USD, BTCUSD, BTC-USDT...) to Binance's
    pair format (BTCUSDT). Returns None if not a recognized crypto symbol.
    """
    base = crypto_base(symbol)
    return f"{base}USDT" if base else None


def _fetch_klines_paginated(binance_symbol: str, start_ms: int, end_ms: int) -> list:
    """Fetch all klines between start_ms and end_ms, paginating past
    Binance's 1000-candle-per-request cap. Each batch's last candle
    timestamp seeds the next batch's startTime (+1ms to avoid re-fetching
    the same candle twice).
    """
    all_rows: list = []
    current_start = start_ms

    while current_start < end_ms:
        params = {
            "symbol": binance_symbol,
            "interval": "1d",
            "startTime": current_start,
            "endTime": end_ms,
            "limit": _MAX_LIMIT,
        }
        resp = requests.get(_BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        batch = resp.json()

        if not batch:
            break  # No more data in range.

        all_rows.extend(batch)

        last_open_time = batch[-1][0]  # First column: kline open time (ms)
        current_start = last_open_time + 1  # Advance past the last candle.

        # Fewer rows than the cap means we've reached the end of available data.
        if len(batch) < _MAX_LIMIT:
            break

    return all_rows


def get_binance_stock(
    symbol: str,
    start_date: str,
    end_date: str,
):
    """Fetch daily OHLCV from Binance's public klines endpoint.

    Mirrors get_YFin_data_online's contract: same params, same header +
    CSV-string return shape, same NoMarketDataError-on-empty behavior.
    """
    binance_symbol = _to_binance_symbol(symbol)
    if binance_symbol is None:
        raise NoMarketDataError(
            symbol, symbol, "not a recognized crypto symbol for Binance"
        )

    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start_ms = int(start_dt.timestamp() * 1000)
    # Request one extra day past end_date, then filter locally — this
    # guarantees end_date is included regardless of whether Binance's
    # endTime boundary is inclusive or exclusive (unverified either way;
    # local filtering makes the boundary semantics irrelevant).
    end_ms_buffered = int((end_dt.timestamp() + 86400) * 1000)

    raw = _fetch_klines_paginated(binance_symbol, start_ms, end_ms_buffered)

    if not raw:
        raise NoMarketDataError(
            symbol, binance_symbol, f"no rows between {start_date} and {end_date}"
        )

    data = pd.DataFrame(raw, columns=[
        "Open Time", "Open", "High", "Low", "Close", "Volume",
        "Close Time", "Quote Asset Volume", "Number of Trades",
        "Taker Buy Base", "Taker Buy Quote", "Unused",
    ])
    data["Date"] = pd.to_datetime(data["Open Time"], unit="ms")
    data = data.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]]
    data = data.astype(float)
    data[["Open", "High", "Low", "Close"]] = data[["Open", "High", "Low", "Close"]].round(2)

    # Local filter: drop anything past end_date, regardless of what
    # Binance's boundary actually returned, and drop duplicate rows that
    # can arise at pagination batch boundaries.
    data = data[~data.index.duplicated(keep="first")]
    data = data[data.index.date <= end_dt.date()]

    if data.empty:
        raise NoMarketDataError(
            symbol, binance_symbol, f"no rows between {start_date} and {end_date}"
        )

    csv_string = data.to_csv()
    header = f"# Stock data for {binance_symbol} (from {symbol}) from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string