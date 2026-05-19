"""Akshare-based stock data fetchers for China A-share market.

Provides OHLCV price data and technical indicator calculations with the
same function signatures as the yfinance-based implementations, so the
vendor routing in ``interface.py`` can swap them transparently.
"""

from __future__ import annotations

import math
import sys
import time
from datetime import datetime
from typing import Annotated

import pandas as pd

# ── Block mini-racer (V8 JS engine) from loading ────────────────────────
# akshare bundles mini-racer as a dependency, but it crashes with SIGTRAP
# on macOS ARM64 (address_pool_manager.cc FATAL). Since our data calls
# don't need JS execution, we inject a dummy module to prevent loading.
import types as _types

_dummy_mr = _types.ModuleType("mini_racer")
_dummy_mr.__version__ = "0.0.0-blocked"
_dummy_mr.MiniRacer = type("MiniRacer", (), {"__init__": lambda s, *a, **k: None})
sys.modules.setdefault("mini_racer", _dummy_mr)
sys.modules.setdefault("py_mini_racer", _dummy_mr)

from .a_share_common import (
    ensure_ipv4,
    format_date_for_api,
    get_previous_trade_date,
    normalize_ashare_symbol,
    to_plain_code,
    to_exchange_prefix,
)
from .config import get_config
from .utils import safe_ticker_component


# ── Akshare retry helper ────────────────────────────────────────────────

def _ak_retry_pre_delay():
    """Randomized pre-delay to avoid rate limiting."""
    import random
    time.sleep(0.5 + random.random())


def _ak_retry(func, *args, max_retries: int = 3, base_delay: float = 2.0, **kwargs):
    """Call an akshare function with retry on transient network errors.

    Includes a pre-call delay to avoid hitting East Money rate limits
    when multiple akshare functions are called in quick succession.
    """
    import requests
    import random

    _ak_retry_pre_delay()

    last_exc = None
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (
            requests.exceptions.RequestException,
            ConnectionError,
            TimeoutError,
        ) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.random()
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ── OHLCV data ──────────────────────────────────────────────────────────

def _download_ohlcv_tencent(
    symbol: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """Download daily OHLCV via Tencent Finance HTTP API directly.

    Bypasses akshare's ``stock_zh_a_hist_tx`` (which uses mini-racer/V8)
    and calls the Tencent Finance API directly via HTTP. This avoids the
    V8 engine crash on macOS ARM64.

    The Tencent API returns the last N days of data (no date-range filter),
    so we request a generous count and filter by date in Python.
    """
    import requests
    import json
    import re

    ensure_ipv4()

    tx_symbol = to_exchange_prefix(symbol).lower()

    # Request last 800 trading days (~3 years) — generous enough for any use
    url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    params = {
        "_var": "kline_dayqfq",
        "param": f"{tx_symbol},day,,,800,qfq",
    }

    _ak_retry_pre_delay()
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()

    # Parse JS variable assignment: kline_dayqfq={...}
    text = resp.text
    match = re.search(r"=\s*(\{.+\})", text, re.DOTALL)
    if not match:
        return pd.DataFrame()

    data = json.loads(match.group(1))
    d = data.get("data", {})
    if isinstance(d, list):
        return pd.DataFrame()  # empty response

    klines = d.get(tx_symbol, {}).get("qfqday", [])
    if not klines:
        return pd.DataFrame()

    # Parse into DataFrame
    rows = []
    for k in klines:
        if len(k) < 6:
            continue
        rows.append({
            "Date": k[0],
            "Open": float(k[1]),
            "Close": float(k[2]),
            "High": float(k[3]),
            "Low": float(k[4]),
            "Volume": int(float(k[5])),
        })

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])

    # Filter by requested date range
    start_dt = pd.Timestamp(start_date)
    end_dt = pd.Timestamp(end_date)
    df = df[(df["Date"] >= start_dt) & (df["Date"] <= end_dt)]

    return df


def _download_ohlcv_akshare(
    symbol: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """Download daily OHLCV via akshare with Tencent fallback.

    Tries East Money (``stock_zh_a_hist``) first. On any connection error
    (rate limiting, network issues), automatically falls back to Tencent
    (``stock_zh_a_hist_tx``).

    The returned columns match what stockstats expects: Date, Open, High,
    Low, Close, Volume.
    """
    ensure_ipv4()
    import akshare as ak

    code = to_plain_code(symbol)

    # ── Primary: East Money ──
    try:
        df = _ak_retry(
            ak.stock_zh_a_hist,
            symbol=code,
            period="daily",
            start_date=format_date_for_api(start_date),
            end_date=format_date_for_api(end_date),
            adjust="qfq",
            max_retries=2,
        )
        if df is not None and not df.empty:
            # Chinese column names are from the akshare API response — keys must stay as-is.
            col_map = {
                "日期": "Date",          # Date
                "开盘": "Open",          # Open price
                "最高": "High",          # High price
                "最低": "Low",           # Low price
                "收盘": "Close",         # Close price
                "成交量": "Volume",      # Trading volume
                "成交额": "Amount",      # Trading amount (CNY)
                "振幅": "AmplitudePct",  # Amplitude percentage
                "涨跌幅": "PctChange",   # Price change percentage
                "涨跌额": "PriceChange", # Price change absolute
                "换手率": "TurnoverPct", # Turnover rate percentage
                "股票代码": "Symbol",    # Stock symbol
            }
            df = df.rename(columns=col_map)
            df["Date"] = pd.to_datetime(df["Date"])
            drop_cols = [c for c in ["Symbol"] if c in df.columns]
            return df.drop(columns=drop_cols, errors="ignore")
    except Exception:
        pass  # fall through to Tencent

    # ── Fallback: Tencent ──
    try:
        df = _download_ohlcv_tencent(symbol, start_date, end_date)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass  # fall through to empty

    return pd.DataFrame()


def load_ohlcv_akshare(symbol: str, curr_date: str) -> pd.DataFrame:
    """Fetch OHLCV data via akshare with caching, filtered to *curr_date*.

    Drop-in replacement for ``stockstats_utils.load_ohlcv`` when the
    akshare vendor is active. Uses the same caching strategy (CSV file
    per symbol under ``data_cache_dir``).
    """
    from .stockstats_utils import _clean_dataframe

    safe_symbol = safe_ticker_component(symbol)
    config = get_config()
    curr_date_dt = pd.to_datetime(curr_date)

    # 5-year lookback, same as the yfinance version
    today = pd.Timestamp.today()
    start = today - pd.DateOffset(years=5)
    start_str = start.strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")

    import os

    cache_dir = config["data_cache_dir"]
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(
        cache_dir, f"{safe_symbol}-AkShare-data-{start_str}-{end_str}.csv"
    )

    if os.path.exists(cache_file):
        data = pd.read_csv(cache_file, on_bad_lines="skip", encoding="utf-8")
    else:
        data = _download_ohlcv_akshare(symbol, start_str, end_str)
        if data.empty:
            return data
        data.to_csv(cache_file, index=False, encoding="utf-8")

    data = _clean_dataframe(data)
    # Prevent look-ahead bias
    data = data[data["Date"] <= curr_date_dt]
    return data


# ── Public API (same signatures as yfinance) ────────────────────────────

def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve A-share OHLCV data via akshare.

    Compatible with the ``get_stock_data`` vendor interface.
    """
    normalized = normalize_ashare_symbol(symbol)
    try:
        df = _download_ohlcv_akshare(symbol, start_date, end_date)
    except Exception as exc:
        return (
            f"# A-share price data for {normalized} from {start_date} to {end_date}\n"
            f"# Error: {type(exc).__name__}: {str(exc)[:200]}"
        )

    if df.empty:
        return f"No A-share data found for {normalized} between {start_date} and {end_date}"

    # Round for display
    numeric_cols = ["Open", "High", "Low", "Close"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].round(2)

    # Detect which source was used based on Volume column
    has_volume = "Volume" in df.columns and df["Volume"].sum() > 0
    source = "akshare (East Money)" if has_volume else "akshare (Tencent)"

    csv_string = df.to_csv(index=False)
    header = (
        f"# A-share price data for {normalized} from {start_date} to {end_date}\n"
        f"# Total records: {len(df)}\n"
        f"# Data source: {source}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + csv_string


def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Retrieve technical indicator values for an A-share stock via akshare.

    Uses stockstats for calculation (same as the yfinance vendor), but
    fetches underlying OHLCV data from akshare.
    """
    from stockstats import wrap

    best_ind_params = {
        "close_50_sma": "50 SMA: Medium-term trend indicator for support/resistance.",
        "close_200_sma": "200 SMA: Long-term trend benchmark for golden/death cross.",
        "close_10_ema": "10 EMA: Responsive short-term average for momentum shifts.",
        "macd": "MACD: Momentum via EMA differences, look for crossovers/divergence.",
        "macds": "MACD Signal: EMA smoothing of MACD line for trade triggers.",
        "macdh": "MACD Histogram: Gap between MACD and signal for momentum strength.",
        "rsi": "RSI: Overbought (>70) / oversold (<30) momentum indicator.",
        "boll": "Bollinger Middle: 20 SMA as dynamic price benchmark.",
        "boll_ub": "Bollinger Upper Band: Overbought / breakout zone.",
        "boll_lb": "Bollinger Lower Band: Oversold / reversal zone.",
        "atr": "ATR: Volatility measure for stop-loss and position sizing.",
        "vwma": "VWMA: Volume-weighted moving average for trend confirmation.",
        "mfi": "MFI: Money Flow Index for volume-weighted overbought/oversold.",
    }

    if indicator not in best_ind_params:
        raise ValueError(
            f"Indicator {indicator} is not supported. "
            f"Choose from: {list(best_ind_params.keys())}"
        )

    # Align to the most recent trading day on or before curr_date
    try:
        aligned_date = get_previous_trade_date(curr_date)
    except Exception:
        aligned_date = curr_date

    end_date = aligned_date
    curr_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
    from dateutil.relativedelta import relativedelta

    before = curr_date_dt - relativedelta(days=look_back_days)

    try:
        data = load_ohlcv_akshare(symbol, end_date)
        if data.empty:
            return f"No A-share data found for {symbol} — cannot compute {indicator}."

        df = wrap(data)
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        df[indicator]  # trigger stockstats calculation

        # Build date→value map
        indicator_data = {}
        for _, row in df.iterrows():
            date_str = row["Date"]
            value = row[indicator]
            indicator_data[date_str] = "N/A" if pd.isna(value) else str(value)

        # Generate output for requested window
        ind_string = ""
        current_dt = curr_date_dt
        while current_dt >= before:
            date_str = current_dt.strftime("%Y-%m-%d")
            if date_str in indicator_data:
                ind_string += f"{date_str}: {indicator_data[date_str]}\n"
            else:
                ind_string += f"{date_str}: N/A (not a trading day)\n"
            current_dt -= relativedelta(days=1)

    except Exception as exc:
        ind_string = f"Error computing {indicator}: {exc}"

    result = (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date} "
        f"(A-share: {normalize_ashare_symbol(symbol)}):\n\n"
        + ind_string
        + "\n\n"
        + best_ind_params.get(indicator, "")
    )
    return result
