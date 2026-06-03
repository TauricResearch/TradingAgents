"""Futu OpenD vendor implementation."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta

from .config import get_config
from .errors import DataVendorError
from .market_snapshot import (
    bars_from_frame,
    format_market_snapshot,
    normalize_ohlcv_frame,
    snapshot_from_bars,
)


def _futu_constants():
    try:
        from futu import KLType  # type: ignore
    except ImportError as e:
        raise DataVendorError("futu-api not installed") from e
    return KLType


def _ctx():
    try:
        from futu import OpenQuoteContext  # type: ignore
    except ImportError as e:
        raise DataVendorError("futu-api not installed") from e
    cfg = get_config()
    try:
        return OpenQuoteContext(
            host=cfg.get("futu_opend_host", "127.0.0.1"),
            port=int(cfg.get("futu_opend_port", 11111)),
        )
    except Exception as e:
        raise DataVendorError(f"Cannot reach OpenD: {e}") from e


def translate_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.endswith(".HK"):
        return f"HK.{s.split('.')[0].zfill(5)}"
    if s.endswith(".SS") or s.endswith(".SH"):
        return f"SH.{s.split('.')[0]}"
    if s.endswith(".SZ"):
        return f"SZ.{s.split('.')[0]}"
    if "." in s or "-" in s:
        raise DataVendorError(f"futu unsupported symbol {symbol}")
    return f"US.{s}"


def _fetch_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    ctx = _ctx()
    try:
        constants = _futu_constants()
        result = ctx.request_history_kline(
            translate_symbol(symbol),
            start=start_date,
            end=end_date,
            ktype=constants.K_DAY,
        )
        ret, data = result[0], result[1]
        if ret != 0:
            raise DataVendorError(f"futu returned error code {ret}")
        return data.rename(columns={"time_key": "timestamp"})
    finally:
        try:
            ctx.close()
        except Exception:
            pass


def fetch_ohlcv_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    frame = _fetch_frame(symbol, start_date, end_date)
    return normalize_ohlcv_frame(frame.rename(columns={"time_key": "timestamp"}), source="futu")


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    df = _fetch_frame(symbol, start_date, end_date)
    clean = pd.DataFrame([bar.__dict__ for bar in bars_from_frame(df, source="futu")])
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
    df = _fetch_frame(ticker, start_date, curr_date)
    snapshot = snapshot_from_bars(
        ticker=ticker,
        requested_date=curr_date,
        source="futu",
        bars=bars_from_frame(df, source="futu"),
        stale_after_seconds=stale_after_seconds,
    )
    return format_market_snapshot(snapshot)


def get_options_chain(symbol: str, expiration: str = "") -> str:
    raise DataVendorError("futu.get_options_chain is not implemented")
