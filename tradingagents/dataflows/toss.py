"""Toss Securities market-data vendor.

Implements the two market-data tools the framework routes through a vendor
(``get_stock_data`` and ``get_indicators``) on top of the Toss daily candle
endpoint. Output formats mirror the yfinance vendor so the agents see identical
report shapes regardless of source.

Symbols are passed through verbatim: KRX uses 6-digit codes (e.g. ``005930``),
US uses plain tickers (e.g. ``AAPL``).
"""

from typing import Annotated
from datetime import datetime

import pandas as pd

from .toss_client import TossClient
from .stockstats_utils import render_indicator_window

# Toss caps candle responses at 200 bars/request. The longest indicator
# warm-up we support is the 200 SMA, so we pull enough history to cover that
# plus the requested look-back window with margin.
_MIN_WARMUP_BARS = 260

# Per-process cache: one daily OHLCV frame per (symbol, curr_date). A single
# analysis run computes many indicators for the same symbol/date; this avoids
# re-paginating the candle endpoint each time.
_candles_cache: dict = {}


def _toss_symbol(symbol: str) -> str:
    """Normalize to the Toss order symbol.

    Korean tickers may arrive in yfinance form (``005490.KS`` / ``.KQ``) because
    the fundamentals/news vendor needs that suffix; Toss uses the bare 6-digit
    code. Stripping it here lets a single ticker flow through both vendors.
    """
    if symbol.endswith((".KS", ".KQ")):
        return symbol[:-3]
    return symbol


def _fetch_daily_candles(symbol: str, min_bars: int) -> pd.DataFrame:
    """Page through the daily candle endpoint until at least ``min_bars`` bars.

    Returns a DataFrame with columns Date/Open/High/Low/Close/Volume sorted
    ascending by date. Candles arrive newest-first; we paginate via ``nextBefore``.
    """
    client = TossClient.instance()
    rows = []
    before = None

    while len(rows) < min_bars:
        params = {"symbol": symbol, "interval": "1d", "count": 200, "adjusted": "true"}
        if before:
            params["before"] = before
        result = client.request("GET", "/api/v1/candles", params=params)["result"]
        page = result.get("candles", [])
        rows.extend(page)
        before = result.get("nextBefore")
        if not before or not page:
            break

    if not rows:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])

    df = pd.DataFrame(rows)
    df = df.rename(
        columns={
            "timestamp": "Date",
            "openPrice": "Open",
            "highPrice": "High",
            "lowPrice": "Low",
            "closePrice": "Close",
            "volume": "Volume",
        }
    )
    # Daily candle timestamps are the bar's local market open (e.g.
    # 2026-06-11T00:00:00+09:00); the trading day is the local date. Take the
    # date portion directly to avoid a UTC conversion shifting it by a day.
    df["Date"] = pd.to_datetime(df["Date"].str[:10])
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Close"]).drop_duplicates(subset=["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    return df[["Date", "Open", "High", "Low", "Close", "Volume"]]


def _load_candles(symbol: str, curr_date: str, min_bars: int) -> pd.DataFrame:
    """Return daily candles up to ``curr_date`` (inclusive), cached per run.

    Filtering to curr_date prevents look-ahead bias, matching the yfinance
    loader's behaviour.
    """
    curr_dt = pd.to_datetime(curr_date).normalize()
    cache_key = (symbol, curr_dt)
    df = _candles_cache.get(cache_key)
    if df is None:
        df = _fetch_daily_candles(symbol, min_bars)
        _candles_cache[cache_key] = df
    return df[df["Date"] <= curr_dt]


def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Daily OHLCV between start_date and end_date as a CSV report string."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")
    symbol = _toss_symbol(symbol)

    start_dt = pd.to_datetime(start_date).normalize()
    end_dt = pd.to_datetime(end_date).normalize()
    span_days = (end_dt - start_dt).days
    # Calendar span overshoots trading days; cap at the warm-up floor.
    min_bars = max(span_days + 5, _MIN_WARMUP_BARS)

    df = _load_candles(symbol, end_date, min_bars)
    df = df[(df["Date"] >= start_dt) & (df["Date"] <= end_dt)]

    if df.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    out = df.copy()
    out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")
    for col in ["Open", "High", "Low", "Close"]:
        out[col] = out[col].round(2)
    csv_string = out.to_csv(index=False)

    header = f"# Stock data for {symbol} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(out)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_string


def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """One technical indicator over a look-back window, as a report string."""
    symbol = _toss_symbol(symbol)
    min_bars = _MIN_WARMUP_BARS + look_back_days
    df = _load_candles(symbol, curr_date, min_bars)
    if df.empty:
        return f"No data found for symbol '{symbol}' up to {curr_date}"
    return render_indicator_window(df, indicator, curr_date, look_back_days)
