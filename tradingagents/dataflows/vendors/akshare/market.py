"""AKShare market data backed by Sina Finance's public endpoints.

Free and keyless. Sina endpoints serve both mainland-China and overseas
clients, unlike Eastmoney-backed akshare calls (``stock_us_hist`` etc.)
whose server-side rate limiting is IP-independent. US symbols use
``ak.stock_us_daily``; A-share symbols (``sh600519`` style) use
``ak.stock_zh_a_daily``. Both are adjusted ("qfq") daily bars.
"""

from __future__ import annotations

import re
import threading
import time as _time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Annotated
import logging

import pandas as pd

from tradingagents.dataflows.errors import NoMarketDataError, VendorError
from tradingagents.dataflows.vendors.yahoo.market import BEST_IND_PARAMS
from tradingagents.dataflows.vendors.yahoo.ohlcv import (
    _clean_dataframe,
    _fill_price_gaps,
    raise_for_empty,
)

try:
    import akshare as ak

    _AKSHARE_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - optional dependency
    ak = None
    _AKSHARE_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)

_A_SHARE_SYMBOL = re.compile(r"^(sh|sz|bj)\d{6}$", re.IGNORECASE)

# In-process cache so one analysis run (1 price pull + N indicator pulls +
# 1 snapshot per symbol) hits Sina once instead of N times. TTL mirrors the
# yfinance vendor's OHLCV cache window; daily-bar analysis tolerates the lag.
_CACHE_TTL_SECONDS = 900.0
_ohlcv_cache: dict[str, tuple[float, "pd.DataFrame"]] = {}
_ohlcv_cache_lock = threading.Lock()

_RENAME_COLUMNS = {
    "date": "Date",
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume",
}


def _fetch_ohlcv(symbol: str) -> pd.DataFrame:
    """Load daily OHLCV from Sina via akshare, cleaned for stockstats."""
    if ak is None:
        raise NoMarketDataError(
            symbol, symbol, f"akshare is not installed: {_AKSHARE_IMPORT_ERROR}"
        )
    key = symbol.strip().lower()
    now = _time.monotonic()
    with _ohlcv_cache_lock:
        hit = _ohlcv_cache.get(key)
        if hit is not None and now - hit[0] < _CACHE_TTL_SECONDS:
            return hit[1].copy()

    raw_symbol = symbol.strip()
    try:
        if _A_SHARE_SYMBOL.match(raw_symbol):
            data = ak.stock_zh_a_daily(symbol=raw_symbol.lower(), adjust="qfq")
        else:
            data = ak.stock_us_daily(symbol=raw_symbol.upper(), adjust="qfq")
    except IndexError as exc:
        # Sina's parser surfaces unknown tickers as a bare IndexError.
        raise NoMarketDataError(
            symbol,
            symbol.upper(),
            "symbol not recognized by Sina (supports US tickers like NVDA and "
            "A-share codes like sh600519/sz000001/bj920099)",
        ) from exc
    except Exception as exc:
        raise NoMarketDataError(
            symbol, symbol, f"akshare request failed: {exc}"
        ) from exc

    data = data.rename(columns=_RENAME_COLUMNS)
    data = _clean_dataframe(data)
    data = _fill_price_gaps(data)
    if data.empty:
        raise_for_empty(symbol, symbol.upper(), "rows after cleaning")
    frame = data.reset_index(drop=True)
    with _ohlcv_cache_lock:
        _ohlcv_cache[key] = (now, frame)
    return frame.copy()


def get_akshare_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Daily OHLCV for ``symbol`` between the requested dates, as CSV text."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    data = _fetch_ohlcv(symbol)
    in_window = (data["Date"] >= pd.to_datetime(start_date)) & (
        data["Date"] <= pd.to_datetime(end_date)
    )
    window = data.loc[in_window]
    if window.empty:
        raise_for_empty(
            symbol, symbol.upper(), f"rows between {start_date} and {end_date}"
        )

    out = window[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    for col in ("Open", "High", "Low", "Close"):
        out[col] = out[col].round(2)
    out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")

    header = (
        f"# Stock data for {symbol.upper()} from {start_date} to {end_date}"
        " (akshare/Sina)\n"
    )
    header += f"# Total records: {len(out)}\n\n"
    return header + out.to_csv(index=False)


def _akshare_indicator_series(symbol: str, indicator: str) -> dict[str, str]:
    """Compute one indicator over the full akshare history (date -> value)."""
    from stockstats import wrap

    data = _fetch_ohlcv(symbol)
    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    df[indicator]  # triggers stockstats to calculate the indicator

    result: dict[str, str] = {}
    for _, row in df.iterrows():
        value = row[indicator]
        result[row["Date"]] = "N/A" if pd.isna(value) else str(value)
    return result


def get_akshare_indicators_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[
        str, "The current trading date you are trading on, YYYY-mm-dd"
    ],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """One indicator over a trailing calendar window, formatted like the
    yfinance implementation so downstream prompts stay unchanged."""
    if indicator not in BEST_IND_PARAMS:
        raise ValueError(
            f"Indicator {indicator} is not supported. "
            f"Please choose from: {list(BEST_IND_PARAMS)}"
        )

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    try:
        indicator_data = _akshare_indicator_series(symbol, indicator)
    except VendorError:
        raise

    lines = []
    current_dt = curr_date_dt
    while current_dt >= before:
        date_str = current_dt.strftime("%Y-%m-%d")
        value = indicator_data.get(
            date_str, "N/A: Not a trading day (weekend or holiday)"
        )
        lines.append(f"{date_str}: {value}")
        current_dt = current_dt - relativedelta(days=1)

    return (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(lines)
        + "\n\n"
        + BEST_IND_PARAMS.get(indicator, "No description available.")
    )


def _fetch_ohlcv_raw(symbol: str) -> pd.DataFrame:
    """Cleaned OHLCV without gap filling (verification semantics)."""
    if ak is None:
        raise NoMarketDataError(
            symbol, symbol, f"akshare is not installed: {_AKSHARE_IMPORT_ERROR}"
        )
    raw_symbol = symbol.strip()
    try:
        if _A_SHARE_SYMBOL.match(raw_symbol):
            data = ak.stock_zh_a_daily(symbol=raw_symbol.lower(), adjust="qfq")
        else:
            data = ak.stock_us_daily(symbol=raw_symbol.upper(), adjust="qfq")
    except IndexError as exc:
        raise NoMarketDataError(
            symbol,
            symbol.upper(),
            "symbol not recognized by Sina (supports US tickers like NVDA and "
            "A-share codes like sh600519/sz000001/bj920099)",
        ) from exc
    except Exception as exc:
        raise NoMarketDataError(
            symbol, symbol, f"akshare request failed: {exc}"
        ) from exc
    data = _clean_dataframe(data.rename(columns=_RENAME_COLUMNS))
    data = data.dropna(subset=["Close"])
    if data.empty:
        raise_for_empty(symbol, symbol.upper(), "price rows")
    return data.reset_index(drop=True)


def build_akshare_verified_market_snapshot(
    symbol: str,
    curr_date: str,
    look_back_days: int = 30,
    indicators=None,
) -> str:
    """Same shape as the yfinance snapshot, computed from Sina data."""
    from stockstats import wrap

    from tradingagents.dataflows.vendors.yahoo.snapshot import (
        DEFAULT_SNAPSHOT_INDICATORS,
        _fmt,
    )

    df = _fetch_ohlcv_raw(symbol)
    df = df[df["Date"] <= pd.to_datetime(curr_date)].sort_values("Date")
    if df.empty:
        raise NoMarketDataError(
            symbol, symbol.upper(), f"rows on or before {curr_date}"
        )

    stock_df = wrap(df.copy())
    selected = tuple(indicators or DEFAULT_SNAPSHOT_INDICATORS)
    indicator_values: dict[str, str] = {}
    for name in selected:
        try:
            stock_df[name]
            indicator_values[name] = _fmt(stock_df.iloc[-1][name])
        except Exception as exc:
            indicator_values[name] = f"N/A ({type(exc).__name__})"

    latest = df.iloc[-1]
    window = max(1, min(int(look_back_days), 30))
    recent = df.tail(window)

    lines = [
        f"## Verified market data snapshot for {symbol.upper()}",
        "",
        f"- Requested analysis date: {curr_date}",
        f"- Latest trading row used: {_fmt(latest['Date'])}",
        "- Rows after the requested analysis date are excluded before verification.",
        "",
        "### Latest verified OHLCV row",
        "",
        "| Field | Value |",
        "|---|---:|",
    ]
    for field in ("Open", "High", "Low", "Close", "Volume"):
        lines.append(f"| {field} | {_fmt(latest.get(field))} |")
    lines += ["", "### Verified technical indicators (latest row)", "",
              "| Indicator | Value |", "|---|---:|"]
    for name, value in indicator_values.items():
        lines.append(f"| {name} | {value} |")
    lines += ["", f"### Recent verified closes (last {len(recent)} rows)", "",
              "| Date | Close |", "|---|---:|"]
    for _, row in recent.iterrows():
        lines.append(f"| {_fmt(row['Date'])} | {_fmt(row.get('Close'))} |")
    lines += [
        "",
        "Use this snapshot as the source of truth for exact OHLCV, price-level, "
        "and indicator-value claims. If another tool output conflicts with it, "
        "flag the discrepancy rather than inventing a reconciled number. Do not "
        "claim historical validation, support/resistance bounces, or exact "
        "percentage moves unless directly supported by tool output with concrete "
        "dates and prices.",
    ]
    return "\n".join(lines)
