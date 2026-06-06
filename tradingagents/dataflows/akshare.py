from __future__ import annotations

from datetime import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta

from tradingagents.dataflows.market_snapshot import (
    MarketDataUnavailable,
    bars_from_frame,
    format_market_snapshot,
    normalize_ohlcv_frame,
    snapshot_from_bars,
)


def _ak():
    try:
        import akshare as ak  # type: ignore
    except ImportError as exc:
        raise MarketDataUnavailable("akshare package is not installed") from exc
    return ak


def _compact_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d")


def _market(symbol: str) -> tuple[str, str]:
    s = symbol.strip().upper()
    if s.endswith(".SS") or s.endswith(".SH"):
        return "cn", s.split(".")[0]
    if s.endswith(".SZ"):
        return "cn", s.split(".")[0]
    if s.endswith(".HK"):
        return "hk", s.split(".")[0].zfill(5)
    if "-" in s:
        raise MarketDataUnavailable(f"akshare unsupported symbol {symbol}")
    return "us", s


def _fetch_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    market, code = _market(symbol)
    ak = _ak()
    if market == "us":
        df = ak.stock_us_daily(symbol=code, adjust="")
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        return df[(df["date"] >= start) & (df["date"] <= end)]
    if market == "cn":
        return ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=_compact_date(start_date),
            end_date=_compact_date(end_date),
            adjust="",
        )
    if market == "hk":
        return ak.stock_hk_hist(
            symbol=code,
            period="daily",
            start_date=_compact_date(start_date),
            end_date=_compact_date(end_date),
            adjust="",
        )
    raise MarketDataUnavailable(f"akshare unsupported symbol {symbol}")


def fetch_ohlcv_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    return normalize_ohlcv_frame(_fetch_frame(symbol, start_date, end_date), source="akshare")


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    df = _fetch_frame(symbol, start_date, end_date)
    clean = pd.DataFrame([bar.__dict__ for bar in bars_from_frame(df, source="akshare")])
    if clean.empty:
        raise MarketDataUnavailable(
            f"akshare returned empty OHLCV for {symbol} between "
            f"{start_date} and {end_date}"
        )
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
        source="akshare",
        bars=bars_from_frame(df, source="akshare"),
        stale_after_seconds=stale_after_seconds,
    )
    return format_market_snapshot(snapshot)
