"""Baostock data provider for Chinese A-shares.

Provides OHLCV, technical indicators, and basic fundamentals for Shanghai and
Shenzhen listed stocks via the free baostock library (http://baostock.com).

Registered as the ``baostock`` vendor in :mod:`interface.py` so it can be
selected via ``data_vendors.core_stock_apis = "baostock"`` in the config.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

import baostock as bs
import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_bs_code(symbol: str) -> str:
    """Normalise a ticker symbol to a baostock code like ``sh.600519``.

    Accepted inputs:
    * ``sh.600519`` / ``sz.000001`` — returned as-is (lowercased)
    * ``600519`` / ``000001`` — exchange inferred from first digit
    * ``600519.SS`` / ``000001.SZ`` — stripped and normalised
    """
    sym = symbol.strip()
    if sym.startswith(("sh.", "sz.")):
        return sym.lower()
    sym = sym.upper()
    if sym.endswith(".SS"):
        return f"sh.{sym[:-3]}"
    if sym.endswith(".SZ"):
        return f"sz.{sym[:-3]}"
    if sym.isdigit():
        return f"sh.{sym}" if sym.startswith("6") else f"sz.{sym}"
    # Fallback — treat as Shanghai code
    return f"sh.{sym}"


def _ensure_login() -> None:
    """Login to baostock (idempotent)."""
    bs.login()


def _parse_date(date_str: str | None, fallback: datetime | None = None) -> datetime:
    """Parse a YYYY-MM-DD string, falling back to *fallback* (default: today)."""
    if date_str:
        return datetime.strptime(date_str, "%Y-%m-%d")
    return fallback or datetime.now()


# ---------------------------------------------------------------------------
# Core stock data (OHLCV)
# ---------------------------------------------------------------------------

def get_baostock_data_online(
    symbol: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "Start date yyyy-mm-dd"],
    end_date: Annotated[str, "End date yyyy-mm-dd"],
) -> str:
    """Fetch daily OHLCV data via baostock, returning a CSV string."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    _ensure_login()
    code = _to_bs_code(symbol)

    rs = bs.query_history_k_data_plus(
        code,
        "date,open,high,low,close,volume,amount,turn",
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="2",  # forward-adjusted (前复权)
    )

    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())

    if not rows:
        return f"No data found for '{symbol}' ({code}) between {start_date} and {end_date}"

    df = pd.DataFrame(rows, columns=rs.fields)
    for col in ("open", "high", "low", "close", "volume", "amount", "turn"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    })
    df["Adj Close"] = df["Close"]

    csv_string = df.to_csv(index=False)
    header = f"# Stock data for {symbol} ({code}) from {start_date} to {end_date}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data source: baostock\n"
    header += f"# Retrieved: {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
    return header + csv_string


# ---------------------------------------------------------------------------
# Technical indicators (stockstats on baostock OHLCV)
# ---------------------------------------------------------------------------

# Descriptions for supported indicators (same set as y_finance.py).
_INDICATOR_DESCRIPTIONS: dict[str, str] = {
    "close_50_sma": "50 SMA: medium-term trend indicator.",
    "close_200_sma": "200 SMA: long-term trend benchmark.",
    "close_10_ema": "10 EMA: responsive short-term average.",
    "macd": "MACD: momentum via EMA differences.",
    "macds": "MACD Signal: EMA smoothing of MACD.",
    "macdh": "MACD Histogram: gap between MACD and signal.",
    "rsi": "RSI: momentum overbought/oversold.",
    "boll": "Bollinger Middle: 20 SMA basis.",
    "boll_ub": "Bollinger Upper Band.",
    "boll_lb": "Bollinger Lower Band.",
    "atr": "ATR: volatility measure.",
    "vwma": "VWMA: volume-weighted moving average.",
    "mfi": "MFI: money flow index.",
}


def get_baostock_indicators_window(
    symbol: Annotated[str, "ticker symbol"],
    indicator: Annotated[str, "technical indicator"],
    curr_date: Annotated[str, "current date YYYY-mm-dd"],
    look_back_days: Annotated[int, "look back days"],
) -> str:
    """Calculate technical indicators using stockstats on baostock data."""
    from dateutil.relativedelta import relativedelta
    from stockstats import wrap

    if indicator not in _INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator {indicator!r} not supported. "
            f"Choose from: {list(_INDICATOR_DESCRIPTIONS)}"
        )

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    # Fetch extra history so stockstats has enough lookback for the indicator
    fetch_start = (curr_date_dt - relativedelta(days=look_back_days + 365)).strftime("%Y-%m-%d")

    _ensure_login()
    code = _to_bs_code(symbol)
    rs = bs.query_history_k_data_plus(
        code, "date,open,high,low,close,volume",
        start_date=fetch_start, end_date=curr_date,
        frequency="d", adjustflag="2",
    )
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return f"No data for {symbol} ({code}) to compute {indicator}"

    df = pd.DataFrame(rows, columns=rs.fields)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.rename(columns={
        "date": "Date", "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Volume",
    })
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    ss = wrap(df)
    ss[indicator]  # trigger lazy calculation

    before = curr_date_dt - relativedelta(days=look_back_days)
    lines: list[str] = []
    current_dt = curr_date_dt
    while current_dt >= before:
        date_str = current_dt.strftime("%Y-%m-%d")
        match = df[df["Date"].dt.strftime("%Y-%m-%d") == date_str]
        if not match.empty:
            lines.append(f"{date_str}: {ss.loc[match.index[0], indicator]}")
        else:
            lines.append(f"{date_str}: N/A (not a trading day)")
        current_dt -= relativedelta(days=1)

    header = f"## {indicator} values from {before:%Y-%m-%d} to {curr_date}:\n\n"
    return header + "\n".join(lines) + "\n\n" + _INDICATOR_DESCRIPTIONS[indicator]


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------

def get_baostock_fundamentals(
    ticker: Annotated[str, "ticker"],
    curr_date: str | None = None,
) -> str:
    """Basic company info from baostock (name, IPO date, status)."""
    _ensure_login()
    code = _to_bs_code(ticker)

    rs = bs.query_stock_basic(code=code)
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())

    if not rows:
        return f"No basic data for {ticker} ({code})"

    info = dict(zip(rs.fields, rows[0]))
    lines = [
        f"# Company Fundamentals for {ticker} ({code})",
        f"# Data source: baostock",
        "",
        f"Code: {info.get('code', 'N/A')}",
        f"Name (CN): {info.get('code_name', 'N/A')}",
        f"IPO Date: {info.get('ipoDate', 'N/A')}",
        f"Out Date: {info.get('outDate', 'N/A') or 'N/A'}",
        f"Type: {info.get('type', 'N/A')}",
        f"Status: {info.get('status', 'N/A')}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Financial statements (profit data via baostock)
# ---------------------------------------------------------------------------

def _query_profit(ticker: str, freq: str, curr_date: str | None) -> pd.DataFrame:
    """Query profit data for the period containing *curr_date*."""
    _ensure_login()
    code = _to_bs_code(ticker)
    dt = _parse_date(curr_date)

    if freq == "quarterly":
        year, quarter = dt.year, (dt.month - 1) // 3 + 1
        rs = bs.query_profit_data(code=code, year=year, quarter=quarter)
    else:
        # Annual — baostock only supports quarterly profit data; try Q4
        rs = bs.query_profit_data(code=code, year=dt.year, quarter=4)

    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=rs.fields)


def get_baostock_balance_sheet(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None,
) -> str:
    """Balance-sheet data via baostock profit query."""
    df = _query_profit(ticker, freq, curr_date)
    if df.empty:
        return f"No balance-sheet data for {ticker} ({_to_bs_code(ticker)})"
    return f"# Balance Sheet for {ticker} ({freq})\n\n{df.to_csv(index=False)}"


def get_baostock_cashflow(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None,
) -> str:
    """Cash-flow data — not available via baostock."""
    return f"# Cash-flow data not available via baostock for {ticker}"


def get_baostock_income_statement(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None,
) -> str:
    """Income-statement data via baostock profit query."""
    df = _query_profit(ticker, freq, curr_date)
    if df.empty:
        return f"No income-statement data for {ticker} ({_to_bs_code(ticker)})"
    return f"# Income Statement for {ticker} ({freq})\n\n{df.to_csv(index=False)}"


# ---------------------------------------------------------------------------
# News / Insider transactions — stubs (baostock does not provide these)
# ---------------------------------------------------------------------------

def get_baostock_news(ticker: str, start_date: str | None = None, end_date: str | None = None) -> str:
    return f"# News not available via baostock for {ticker}. Use web search instead."


def get_baostock_global_news(*args, **kwargs) -> str:
    return "# Global news not available via baostock. Use web search instead."


def get_baostock_insider_transactions(ticker: str) -> str:
    return f"# Insider transactions not available via baostock for {ticker}."
