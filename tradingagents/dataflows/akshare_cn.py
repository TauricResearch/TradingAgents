from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

import pandas as pd


def _load_akshare():
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError(
            "AKShare is not installed. Run `pip install akshare` first."
        ) from exc
    return ak


def _normalize_a_share_symbol(symbol: str) -> str:
    s = symbol.strip().lower()
    if s.startswith(("sh", "sz", "bj")) and len(s) >= 8:
        return s
    if s.isdigit() and len(s) == 6:
        if s.startswith(("6", "9")):
            return f"sh{s}"
        if s.startswith(("0", "2", "3")):
            return f"sz{s}"
        if s.startswith(("4", "8")):
            return f"bj{s}"
    return s


def _extract_code(symbol: str) -> str:
    norm = _normalize_a_share_symbol(symbol)
    if len(norm) >= 8 and norm[:2] in {"sh", "sz", "bj"}:
        return norm[2:]
    return norm


def get_stock_data_akshare(
    symbol: Annotated[str, "A-share symbol, e.g. 600519 or sh600519"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):
    ak = _load_akshare()
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    code = _extract_code(symbol)
    start = start_date.replace("-", "")
    end = end_date.replace("-", "")

    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="qfq",
        )
    except Exception as exc:
        return f"Error fetching A-share stock data for {symbol}: {exc}"

    if df is None or df.empty:
        return f"No A-share data found for symbol '{symbol}' between {start_date} and {end_date}"

    rename_map = {
        "日期": "Date",
        "开盘": "Open",
        "收盘": "Close",
        "最高": "High",
        "最低": "Low",
        "成交量": "Volume",
        "成交额": "Amount",
        "振幅": "Amplitude",
        "涨跌幅": "ChangePct",
        "涨跌额": "Change",
        "换手率": "Turnover",
    }
    out = df.rename(columns=rename_map)
    header = (
        f"# A-share stock data for {symbol} ({code}) from {start_date} to {end_date}\n"
        f"# Total records: {len(out)}\n"
        f"# Data source: AKShare stock_zh_a_hist\n\n"
    )
    return header + out.to_csv(index=False)


def get_indicator_akshare(
    symbol: Annotated[str, "A-share symbol"],
    indicator: Annotated[str, "technical indicator"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    end_date = curr_date
    start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days * 3)).strftime("%Y-%m-%d")
    raw = get_stock_data_akshare(symbol, start_date, end_date)
    if raw.startswith("No A-share") or raw.startswith("Error"):
        return raw

    csv_part = "\n".join(raw.splitlines()[4:])
    df = pd.read_csv(pd.io.common.StringIO(csv_part))
    if df.empty or "Close" not in df.columns:
        return f"Unable to compute indicator {indicator} for {symbol}"

    close = pd.to_numeric(df["Close"], errors="coerce")

    indicator_lower = indicator.lower()
    if indicator_lower == "rsi":
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, pd.NA)
        series = 100 - (100 / (1 + rs))
    elif indicator_lower in {"close_10_ema", "ema10"}:
        series = close.ewm(span=10, adjust=False).mean()
    elif indicator_lower in {"close_50_sma", "sma50"}:
        series = close.rolling(50).mean()
    elif indicator_lower == "macd":
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        series = ema12 - ema26
    else:
        return (
            f"AKShare adapter currently supports indicators: rsi, close_10_ema, close_50_sma, macd. "
            f"Requested: {indicator}"
        )

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["indicator"] = series
    window_df = df.dropna(subset=["Date"]).tail(look_back_days)
    lines = [f"{d}: {v}" for d, v in zip(window_df["Date"], window_df["indicator"])]
    return f"## {indicator} values for {symbol} up to {curr_date}:\n\n" + "\n".join(lines)


def get_fundamentals_akshare(
    ticker: Annotated[str, "A-share symbol"],
    curr_date: Annotated[str, "current date"] = None,
):
    return (
        "AKShare fundamentals vary by endpoint and exchange. "
        "Recommended: wire dedicated endpoints for balance sheet/cashflow/income statement per your data policy. "
        f"Current symbol: {ticker}."
    )


def get_balance_sheet_akshare(
    ticker: Annotated[str, "A-share symbol"],
    freq: Annotated[str, "quarterly/annual"] = "quarterly",
    curr_date: Annotated[str, "current date"] = None,
):
    return f"AKShare balance-sheet adapter placeholder for {ticker} ({freq})."


def get_cashflow_akshare(
    ticker: Annotated[str, "A-share symbol"],
    freq: Annotated[str, "quarterly/annual"] = "quarterly",
    curr_date: Annotated[str, "current date"] = None,
):
    return f"AKShare cashflow adapter placeholder for {ticker} ({freq})."


def get_income_statement_akshare(
    ticker: Annotated[str, "A-share symbol"],
    freq: Annotated[str, "quarterly/annual"] = "quarterly",
    curr_date: Annotated[str, "current date"] = None,
):
    return f"AKShare income-statement adapter placeholder for {ticker} ({freq})."


def get_news_akshare(
    ticker: Annotated[str, "A-share symbol"],
    start_date: Annotated[str, "Start date"] = None,
    end_date: Annotated[str, "End date"] = None,
):
    return f"AKShare news adapter placeholder for {ticker} from {start_date} to {end_date}."


def get_global_news_akshare(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"] = None,
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
):
    return (
        "AKShare global news adapter placeholder. "
        f"curr_date={curr_date}, look_back_days={look_back_days}, limit={limit}."
    )


def get_insider_transactions_akshare(
    ticker: Annotated[str, "A-share symbol"],
):
    return f"A-share insider transactions adapter placeholder for {ticker}."
