"""Polygon.io vendor implementation.

Plugs into ``route_to_vendor`` via the standard ``VENDOR_METHODS`` registry.
Every public function MUST raise :class:`DataVendorError` (not a generic
exception) on auth/config/network failure so the router falls back to the
next configured vendor instead of failing the whole run.

To activate: set ``POLYGON_API_KEY`` in the environment and add ``"polygon"``
to the relevant ``data_vendors`` / ``tool_vendors`` entry in DEFAULT_CONFIG
(e.g. ``"options_data": "polygon, yfinance"`` for primary-with-fallback).

NOTE: Bodies are intentionally minimal stubs — they implement the request
shape and error handling but do not parse responses into the framework's
expected Markdown format yet. Fill in the formatting (see
``yfinance_options.get_options_overview`` / ``y_finance.get_YFin_data_online``
for reference shapes) before flipping the default category vendor.
"""

import os
from datetime import datetime
from typing import Any, Dict

import pandas as pd
import requests
from dateutil.relativedelta import relativedelta

from .errors import DataVendorError
from .market_snapshot import (
    bars_from_frame,
    format_market_snapshot,
    normalize_ohlcv_frame,
    snapshot_from_bars,
)

_BASE = "https://api.polygon.io"


def _key() -> str:
    k = os.environ.get("POLYGON_API_KEY")
    if not k:
        raise DataVendorError("POLYGON_API_KEY not set")
    return k


def _get(path: str, **params: Any) -> Dict[str, Any]:
    params["apiKey"] = _key()
    try:
        r = requests.get(f"{_BASE}{path}", params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise DataVendorError(f"Polygon request failed: {e}") from e


def _aggs_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    data = _get(
        f"/v2/aggs/ticker/{symbol.upper()}/range/1/day/{start_date}/{end_date}",
        adjusted="true",
        sort="asc",
        limit=5000,
    )
    rows = []
    for item in data.get("results", []):
        rows.append(
            {
                "timestamp": pd.to_datetime(item["t"], unit="ms", utc=True),
                "open": item.get("o"),
                "high": item.get("h"),
                "low": item.get("l"),
                "close": item.get("c"),
                "volume": item.get("v"),
            }
        )
    return pd.DataFrame(rows)


def fetch_ohlcv_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    return normalize_ohlcv_frame(_aggs_frame(symbol, start_date, end_date), source="polygon")


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """OHLCV bars via /v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}."""
    df = _aggs_frame(symbol, start_date, end_date)
    clean = pd.DataFrame([bar.__dict__ for bar in bars_from_frame(df, source="polygon")])
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(clean)}\n\n"
    return header + clean.to_csv(index=False)


def get_market_snapshot(
    ticker: str,
    curr_date: str,
    lookback_days: int = 10,
    stale_after_seconds: int = 900,
) -> str:
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr_dt - relativedelta(days=lookback_days)).strftime("%Y-%m-%d")
    snapshot = snapshot_from_bars(
        ticker=ticker,
        requested_date=curr_date,
        source="polygon",
        bars=bars_from_frame(_aggs_frame(ticker, start_date, curr_date), source="polygon"),
        stale_after_seconds=stale_after_seconds,
    )
    return format_market_snapshot(snapshot)


def get_options_chain(symbol: str, expiration: str = "") -> str:
    """Options snapshot via /v3/snapshot/options/{symbol}.

    TODO: format strike, IV, greeks (delta/gamma/theta/vega), OI, volume
    into the same Markdown shape as ``yfinance_options.get_options_chain``."""
    _get(f"/v3/snapshot/options/{symbol}")
    raise DataVendorError("polygon.get_options_chain: response formatter not implemented yet")


def get_options_overview(symbol: str) -> str:
    """Aggregate snapshot into expirations, ATM IV, put/call OI ratio."""
    _get(f"/v3/snapshot/options/{symbol}")
    raise DataVendorError("polygon.get_options_overview: response formatter not implemented yet")


def get_news(query: str, start_date: str, end_date: str) -> str:
    """Ticker news via /v2/reference/news?ticker=..."""
    _get(
        "/v2/reference/news",
        ticker=query,
        **{"published_utc.gte": start_date, "published_utc.lte": end_date},
    )
    raise DataVendorError("polygon.get_news: response formatter not implemented yet")
