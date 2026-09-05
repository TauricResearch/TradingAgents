"""akshare-based finance vendor for A-share statements and insider changes."""

from __future__ import annotations

import logging
import re
from datetime import datetime

import pandas as pd

from .errors import NoMarketDataError

logger = logging.getLogger(__name__)


def _sina_stock_symbol(ticker: str) -> str | None:
    match = re.search(r"(\d{6})", ticker)
    if not match:
        return None
    code = match.group(1)
    upper = ticker.upper()
    if upper.endswith((".SS", ".SH")) or code.startswith(("5", "6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def _code(ticker: str) -> str | None:
    match = re.search(r"(\d{6})", ticker)
    return match.group(1) if match else None


def _filter_statement(df: pd.DataFrame, freq: str, curr_date: str | None) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    date_col = next((c for c in df.columns if "报告日" in str(c)), None)
    if not date_col:
        return df
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    if curr_date:
        df = df[df[date_col] <= pd.to_datetime(curr_date)]
    if freq.lower() == "annual":
        df = df[df[date_col].dt.strftime("%m-%d") == "12-31"]
    return df.sort_values(date_col, ascending=False)


def _sina_statement(ticker: str, symbol: str, freq: str, curr_date: str | None) -> str:
    sina_symbol = _sina_stock_symbol(ticker)
    if not sina_symbol:
        raise NoMarketDataError(ticker, ticker, "akshare supports A-shares only")
    try:
        import akshare as ak

        df = ak.stock_financial_report_sina(stock=sina_symbol, symbol=symbol)
    except Exception as exc:  # noqa: BLE001
        logger.warning("akshare %s fetch failed for %s: %s", symbol, ticker, exc)
        raise NoMarketDataError(
            ticker, ticker, f"akshare {symbol} unavailable"
        ) from exc

    df = _filter_statement(df, freq, curr_date)
    if df is None or df.empty:
        raise NoMarketDataError(ticker, ticker, f"akshare returned no {symbol} rows")

    header = f"# {symbol} data for {ticker} ({freq}) via akshare/Sina\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + df.to_csv(index=False)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    return _sina_statement(ticker, "资产负债表", freq, curr_date)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    return _sina_statement(ticker, "现金流量表", freq, curr_date)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    return _sina_statement(ticker, "利润表", freq, curr_date)


def get_insider_transactions(ticker: str) -> str:
    code = _code(ticker)
    if not code:
        raise NoMarketDataError(ticker, ticker, "akshare insider supports A-shares only")
    try:
        import akshare as ak

        if code.startswith(("6", "5", "9")):
            df = ak.stock_share_hold_change_sse(symbol=code)
        else:
            df = ak.stock_share_hold_change_szse(symbol=code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("akshare insider fetch failed for %s: %s", ticker, exc)
        return f"暂无 akshare 高管/股东变动数据（{ticker}）。"

    if df is None or df.empty:
        return f"暂无 akshare 高管/股东变动数据（{ticker}）。"
    header = f"# 高管/股东变动数据 for {ticker} via akshare\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + df.to_csv(index=False)
