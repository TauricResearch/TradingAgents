"""Financial Modeling Prep: daily OHLCV for stocks, indices, FX, commodities and crypto.

One endpoint (``/stable/historical-price-eod/full``) serves every asset class;
only the symbol spelling differs from Yahoo's (``GC=F`` -> ``GCUSD``,
``EURUSD=X`` -> ``EURUSD``, ``BTC-USD`` -> ``BTCUSD``). Needs ``FMP_API_KEY``.

FMP gates some symbols by plan. A gated symbol answers with an error body; it
is reported as no data for that symbol, so the router moves to the next vendor.
"""

import os

import pandas as pd
import requests

from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.net import get_scrubbed
from tradingagents.dataflows.symbols import crypto_base, normalize_symbol
from tradingagents.dataflows.vendors.ohlcv_frame import format_stock_data, indicator_window

API_URL = "https://financialmodelingprep.com/stable/historical-price-eod/full"
REQUEST_TIMEOUT = 30
HISTORY_YEARS = 2  # enough for a 200-day SMA well before the analysis window

# Yahoo futures roots -> FMP's spot-style commodity symbols.
_COMMODITIES = {
    "GC=F": "GCUSD", "SI=F": "SIUSD", "PL=F": "PLUSD", "PA=F": "PAUSD",
    "CL=F": "CLUSD", "BZ=F": "BZUSD", "NG=F": "NGUSD", "HG=F": "HGUSD",
}


class FMPNotConfiguredError(VendorNotConfiguredError):
    pass


def _api_key() -> str:
    key = os.getenv("FMP_API_KEY")
    if not key:
        raise FMPNotConfiguredError("FMP_API_KEY environment variable is not set.")
    return key


def fmp_symbol(symbol: str) -> str:
    """Spell a user/Yahoo symbol the way FMP expects it."""
    canonical = normalize_symbol(symbol)
    if canonical in _COMMODITIES:
        return _COMMODITIES[canonical]
    if canonical.endswith("=X"):
        return canonical[:-2]
    base = crypto_base(canonical)
    if base:
        return f"{base}USD"
    return canonical


def load_daily(symbol: str, as_of_date: str | None = None) -> tuple[pd.DataFrame, str]:
    """Daily bars, oldest first, through ``as_of_date`` (or today)."""
    key = _api_key()
    canonical = fmp_symbol(symbol)
    end = pd.Timestamp(as_of_date) if as_of_date else pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=HISTORY_YEARS)
    params = {"symbol": canonical, "from": start.strftime("%Y-%m-%d"),
              "to": end.strftime("%Y-%m-%d"), "apikey": key}
    try:
        resp = get_scrubbed(API_URL, params=params, timeout=REQUEST_TIMEOUT, secret=key,
                            passthrough=(401, 402, 403, 429))
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"FMP request failed: {exc}") from None
    if resp.status_code == 429:
        raise VendorUnavailableError("FMP rate limit reached")
    if resp.status_code == 401:
        raise FMPNotConfiguredError("FMP rejected the API key (401)")
    # A symbol outside the caller's plan comes back as 402 with a plain-text message,
    # though the response is labelled JSON; read the body only after checking the status.
    try:
        body = resp.json() if resp.content else []
    except ValueError:
        body = resp.text.strip()
    if resp.status_code in (402, 403) or not isinstance(body, list):
        msg = (body.get("Error Message") or body.get("message")) if isinstance(body, dict) else body
        raise NoMarketDataError(symbol, canonical, f"FMP did not serve this symbol: {str(msg)[:160] or resp.status_code}")
    if not body:
        raise NoMarketDataError(symbol, canonical, "FMP returned no rows")
    df = pd.DataFrame(body).rename(columns={
        "date": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
    df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
    df = df.sort_values("Date").drop_duplicates("Date").reset_index(drop=True)
    return df, canonical


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    data, canonical = load_daily(symbol, end_date)
    return format_stock_data(data, symbol, canonical, start_date, end_date, "Financial Modeling Prep")


def get_indicators(symbol: str, indicator: str, as_of_date: str, look_back_days: int) -> str:
    data, canonical = load_daily(symbol, as_of_date)
    return indicator_window(data, symbol, canonical, indicator, as_of_date, look_back_days)
