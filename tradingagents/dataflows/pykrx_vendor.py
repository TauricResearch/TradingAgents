# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""pykrx vendor — Korean stock data via direct KRX queries.

Provides:
- get_stock_data_pykrx: daily OHLCV (matches dataflows.get_stock_data contract)
- get_kr_universe: point-in-time KOSPI/KOSDAQ ticker list (NEW tool)
- get_kr_investor_trading: daily net buy by investor type (NEW tool)
- get_kr_value_factors: daily PER/PBR/dividend yield (NEW tool)

All public functions return CSV-string with header (matches existing dataflows pattern).
Internal _fetch_* functions return DataFrame and are wrapped with @simple_parquet_cache.
"""

from datetime import datetime

import pandas as pd

from ._cache import simple_parquet_cache


def _yyyymmdd(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to 'YYYYMMDD'. Validates input format.

    Strict: requires exact zero-padded YYYY-MM-DD (10 chars). Python's
    strptime alone accepts non-zero-padded inputs like '2024-1-2', so we
    enforce the canonical form before delegating to strptime for value
    validation (e.g. month/day ranges).
    """
    if not isinstance(date_str, str) or len(date_str) != 10 or date_str[4] != "-" or date_str[7] != "-":
        raise ValueError(f"Expected date in canonical YYYY-MM-DD form, got {date_str!r}")
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# OHLCV
# ---------------------------------------------------------------------------


@simple_parquet_cache(kind="ohlcv")
def _fetch_pykrx_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    from pykrx import stock

    df = stock.get_market_ohlcv(_yyyymmdd(start_date), _yyyymmdd(end_date), symbol)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.reset_index().rename(
        columns={
            "날짜": "Date",
            "시가": "Open",
            "고가": "High",
            "저가": "Low",
            "종가": "Close",
            "거래량": "Volume",
            "거래대금": "TradingValue",
            "등락률": "ChangePct",
        }
    )
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    # pykrx 1.2.8 omits TradingValue (거래대금); only project columns that exist.
    base_cols = ["Date", "Open", "High", "Low", "Close", "Volume", "ChangePct"]
    if "TradingValue" in df.columns:
        base_cols.insert(6, "TradingValue")
    return df[[c for c in base_cols if c in df.columns]]


def get_stock_data_pykrx(symbol: str, start_date: str, end_date: str) -> str:
    """Vendor-compatible OHLCV CSV-string for KRX symbols (e.g. '005930')."""
    df = _fetch_pykrx_ohlcv(symbol, start_date, end_date)
    if df.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"
    header = (
        f"# Stock data for {symbol} from {start_date} to {end_date}\n"
        f"# Total records: {len(df)}\n"
        f"# Source: pykrx (KRX)\n"
        f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + df.to_csv(index=False)


# ---------------------------------------------------------------------------
# Universe (point-in-time ticker list)
# ---------------------------------------------------------------------------


@simple_parquet_cache(kind="universe")
def _fetch_pykrx_universe(date_str: str, market: str) -> pd.DataFrame:
    from pykrx import stock

    tickers = stock.get_market_ticker_list(_yyyymmdd(date_str), market=market)
    if not tickers:
        return pd.DataFrame()
    rows = []
    for t in tickers:
        try:
            name = stock.get_market_ticker_name(t)
        except Exception:
            name = ""
        rows.append({"ticker": t, "name": name, "market": market, "as_of": date_str})
    return pd.DataFrame(rows)


def get_kr_universe(date_str: str, market: str = "KOSPI") -> str:
    """Point-in-time ticker snapshot for KOSPI / KOSDAQ / KONEX / ALL."""
    df = _fetch_pykrx_universe(date_str, market.upper())
    if df.empty:
        return f"No tickers found for market '{market}' on {date_str}"
    header = (
        f"# KR universe snapshot — market={market}, as_of={date_str}\n"
        f"# Total tickers: {len(df)}\n"
        f"# Source: pykrx (KRX)\n\n"
    )
    return header + df.to_csv(index=False)


# ---------------------------------------------------------------------------
# Investor trading (foreign / institutional / retail net buy)
# ---------------------------------------------------------------------------


@simple_parquet_cache(kind="investor_trading")
def _fetch_pykrx_investor_trading(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    from pykrx import stock

    df = stock.get_market_trading_value_by_date(
        _yyyymmdd(start_date), _yyyymmdd(end_date), symbol
    )
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.reset_index().rename(columns={"날짜": "Date"})
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    return df


def get_kr_investor_trading(symbol: str, start_date: str, end_date: str) -> str:
    """Daily net trading value by investor type (KRW)."""
    df = _fetch_pykrx_investor_trading(symbol, start_date, end_date)
    if df.empty:
        return f"No investor trading data for '{symbol}' between {start_date} and {end_date}"
    header = (
        f"# KR investor trading for {symbol} from {start_date} to {end_date}\n"
        f"# Total records: {len(df)}\n"
        f"# Source: pykrx (KRX)\n\n"
    )
    return header + df.to_csv(index=False)


# ---------------------------------------------------------------------------
# Value factors (PER / PBR / dividend yield)
# ---------------------------------------------------------------------------


@simple_parquet_cache(kind="value_factors")
def _fetch_pykrx_value_factors(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    from pykrx import stock

    df = stock.get_market_fundamental_by_date(
        _yyyymmdd(start_date), _yyyymmdd(end_date), symbol
    )
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.reset_index().rename(columns={"날짜": "Date"})
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    return df


def get_kr_value_factors(symbol: str, start_date: str, end_date: str) -> str:
    """Daily PER / PBR / EPS / BPS / DIV / DPS for a KRX symbol."""
    df = _fetch_pykrx_value_factors(symbol, start_date, end_date)
    if df.empty:
        return f"No value factors for '{symbol}' between {start_date} and {end_date}"
    header = (
        f"# KR value factors for {symbol} from {start_date} to {end_date}\n"
        f"# Total records: {len(df)}\n"
        f"# Source: pykrx (KRX)\n\n"
    )
    return header + df.to_csv(index=False)
