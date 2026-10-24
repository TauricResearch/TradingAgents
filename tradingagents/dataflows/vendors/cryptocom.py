"""Crypto.com Exchange: daily OHLCV for USD-quoted crypto. Public API, no key.

Serves crypto only. Any other symbol is reported as no data, so a chain like
``cryptocom,fmp,yfinance`` sends stocks on to the next vendor.

A daily candle is stamped with its opening time (00:00 UTC). The candle for the
UTC day still trading is left out: its close is not yet a close.
"""

import time

import pandas as pd
import requests

from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.symbols import crypto_base
from tradingagents.dataflows.vendors.ohlcv_frame import format_stock_data, indicator_window

API_URL = "https://api.crypto.com/exchange/v1/public/get-candlestick"
REQUEST_TIMEOUT = 20
PAGE = 300          # the API's per-request maximum
HISTORY_DAYS = 500  # enough for a 200-day SMA well before the analysis window
DAY_MS = 86_400_000


def instrument(symbol: str) -> str | None:
    """``BTC-USD`` / ``BTCUSD`` / ``btc-usdt`` -> ``BTC_USD``; None for non-crypto."""
    base = crypto_base(symbol)
    return f"{base}_USD" if base else None


def _page(name: str, end_ts: int | None) -> list[dict]:
    params = {"instrument_name": name, "timeframe": "1D", "count": PAGE}
    if end_ts:
        params["end_ts"] = end_ts
    try:
        resp = requests.get(API_URL, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"Crypto.com request failed: {exc}") from None
    if resp.status_code == 429 or resp.status_code >= 500:
        raise VendorUnavailableError(f"Crypto.com answered {resp.status_code}")
    body = resp.json()
    if body.get("code") != 0:
        return []
    return body.get("result", {}).get("data", [])


def load_daily(symbol: str, as_of_date: str | None = None) -> tuple[pd.DataFrame, str]:
    """Settled daily bars, oldest first, back ``HISTORY_DAYS`` from ``as_of_date``."""
    name = instrument(symbol)
    if name is None:
        raise NoMarketDataError(symbol, symbol, "Crypto.com serves crypto pairs only")
    end = pd.Timestamp(as_of_date) + pd.Timedelta(days=1) if as_of_date else pd.Timestamp.utcnow().tz_localize(None)
    end_ts = int(end.timestamp() * 1000)
    oldest_wanted = end_ts - HISTORY_DAYS * DAY_MS
    bars: dict[int, dict] = {}
    cursor = end_ts
    while cursor > oldest_wanted:
        page = _page(name, cursor)
        if not page:
            break
        for b in page:
            bars[int(b["t"])] = b
        oldest = min(int(b["t"]) for b in page)
        if oldest >= cursor:
            break
        cursor = oldest
        time.sleep(0.1)  # stay well inside the public rate limit
    now_ms = time.time() * 1000
    rows = [b for t, b in sorted(bars.items()) if t + DAY_MS <= now_ms]  # settled days only
    if not rows:
        raise NoMarketDataError(symbol, name, "Crypto.com returned no settled daily candles")
    df = pd.DataFrame({
        "Date": pd.to_datetime([int(b["t"]) for b in rows], unit="ms").normalize(),
        "Open": [float(b["o"]) for b in rows], "High": [float(b["h"]) for b in rows],
        "Low": [float(b["l"]) for b in rows], "Close": [float(b["c"]) for b in rows],
        "Volume": [float(b["v"]) for b in rows],
    })
    return df, name


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    data, name = load_daily(symbol, end_date)
    return format_stock_data(data, symbol, name, start_date, end_date, "Crypto.com Exchange, UTC days")


def get_indicators(symbol: str, indicator: str, as_of_date: str, look_back_days: int) -> str:
    data, name = load_daily(symbol, as_of_date)
    return indicator_window(data, symbol, name, indicator, as_of_date, look_back_days)
