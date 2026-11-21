"""Hourly OHLCV from Yahoo Finance, cached per symbol and cut at the analysis date.

Yahoo serves hourly bars for roughly the last 730 days. The order-flow
indicators build each session's volume-at-price ladder from these bars, so a
request for a date before the cached history starts is reported as no data
rather than answered from a shorter window.
"""

from __future__ import annotations

import logging
import os

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.files import replace_file
from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component
from tradingagents.dataflows.vendors.yahoo.common import raise_for_empty, yf_retry
from tradingagents.dataflows.vendors.yahoo.ohlcv import OHLCV_CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)

INTERVAL = "1h"
PERIOD = "730d"  # the longest hourly history Yahoo serves


def _naive_local(values) -> pd.Series:
    """Exchange-local wall-clock timestamps without a time zone.

    Each value keeps its own offset (the history spans daylight-saving changes),
    so the zone is dropped per element instead of converting the series to UTC,
    which would move a non-US session onto the previous day.
    """
    def one(value):
        if pd.isna(value):
            return pd.NaT
        try:
            ts = pd.Timestamp(value)
        except (ValueError, TypeError):
            return pd.NaT
        return ts.tz_localize(None) if ts.tzinfo is not None else ts
    return pd.to_datetime(pd.Series(values).map(one))


def _cache_is_fresh(data_file: str, as_of_dt: pd.Timestamp, now: pd.Timestamp) -> bool:
    written = pd.Timestamp.fromtimestamp(os.path.getmtime(data_file))
    if written.date() != now.date():
        return False
    return as_of_dt.date() < now.date() or (now - written).total_seconds() <= OHLCV_CACHE_TTL_SECONDS


def load_intraday(symbol: str, as_of_date: str) -> pd.DataFrame:
    """Hourly bars whose session date is on or before ``as_of_date``.

    Columns: ``Datetime`` (naive exchange-local time of the bar's start),
    ``Session`` (that time's date), ``Open``, ``High``, ``Low``, ``Close``,
    ``Volume``. Raises :class:`NoMarketDataError` when Yahoo has no hourly
    history covering the date.
    """
    canonical = normalize_symbol(symbol)
    safe_symbol = safe_ticker_component(canonical)
    config = get_config()
    as_of_dt = pd.to_datetime(as_of_date).normalize()
    now = pd.Timestamp.today()

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(config["data_cache_dir"], f"{safe_symbol}-YFin-{INTERVAL}.csv")

    data = None
    if os.path.exists(data_file):
        cached = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
        if not cached.empty and "Close" in cached.columns and _cache_is_fresh(data_file, as_of_dt, now):
            data = cached

    if data is None:
        downloaded = yf_retry(lambda: yf.Ticker(canonical).history(
            period=PERIOD, interval=INTERVAL, auto_adjust=True, actions=False,
        ))
        if downloaded is None or downloaded.empty or "Close" not in downloaded.columns:
            raise_for_empty(symbol, canonical, "hourly price rows")
        downloaded = downloaded.reset_index()
        first = downloaded.columns[0]
        downloaded = downloaded.rename(columns={first: "Datetime"})
        replace_file(data_file, lambda temp: downloaded.to_csv(temp, index=False, encoding="utf-8"))
        data = downloaded

    return clean_intraday(data, as_of_date, symbol, canonical)


def clean_intraday(data: pd.DataFrame, as_of_date: str, symbol: str, canonical: str | None = None) -> pd.DataFrame:
    """Parse, sort and cut a raw hourly frame at ``as_of_date`` (inclusive)."""
    df = data.copy()
    if "Datetime" not in df.columns:
        for candidate in ("Date", "index", "datetime"):
            if candidate in df.columns:
                df = df.rename(columns={candidate: "Datetime"})
                break
    if "Volume" not in df.columns:
        df["Volume"] = 0.0
    df["Datetime"] = _naive_local(df["Datetime"])
    for col in ("Open", "High", "Low", "Close", "Volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Datetime", "Open", "High", "Low", "Close"])
    df["Volume"] = df["Volume"].fillna(0.0).clip(lower=0.0)
    df["Session"] = df["Datetime"].dt.normalize()
    as_of_dt = pd.to_datetime(as_of_date).normalize()
    earliest = df["Session"].min() if not df.empty else None
    df = df[df["Session"] <= as_of_dt]
    df = df.sort_values("Datetime").drop_duplicates("Datetime", keep="last").reset_index(drop=True)
    if df.empty:
        detail = (f"hourly history starts on {earliest.date()}, after {as_of_dt.date()}"
                  if earliest is not None and pd.notna(earliest) else "no hourly price rows")
        raise NoMarketDataError(symbol, canonical, detail)
    # How far the hourly bars may trail the daily ones is judged by the caller,
    # which holds both; the daily loader already rejects a stale daily frame.
    return df[["Datetime", "Session", "Open", "High", "Low", "Close", "Volume"]]
