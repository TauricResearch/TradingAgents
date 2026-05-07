import time
import logging
import threading

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError
from stockstats import wrap
from typing import Annotated
import os
from .config import get_config
from .utils import safe_ticker_component

logger = logging.getLogger(__name__)

# How long a cached OHLCV CSV stays fresh before we re-fetch from yfinance.
_CACHE_TTL_SECONDS = 86_400  # 24h

# In-memory cache of wrapped stockstats DataFrames keyed by (symbol, curr_date).
# Avoids re-reading + re-wrapping the CSV per indicator (an analyst pass typically
# requests ~8 indicators, so this cuts I/O and stockstats setup by ~8x).
# Bounded by a simple LRU eviction on insert; per-process state, no cross-process
# sharing needed because each process has its own cache file.
_WRAPPED_CACHE: dict[tuple[str, str], "wrap"] = {}
_WRAPPED_CACHE_ORDER: list[tuple[str, str]] = []
_WRAPPED_CACHE_LOCK = threading.Lock()
_WRAPPED_CACHE_MAX = 16


def _wrapped_cache_get(symbol: str, curr_date: str):
    """Return the cached wrapped DataFrame for (symbol, curr_date), or None."""
    key = (symbol, curr_date)
    with _WRAPPED_CACHE_LOCK:
        df = _WRAPPED_CACHE.get(key)
        if df is not None:
            # Move to end to mark recently used
            try:
                _WRAPPED_CACHE_ORDER.remove(key)
            except ValueError:
                pass
            _WRAPPED_CACHE_ORDER.append(key)
        return df


def _wrapped_cache_put(symbol: str, curr_date: str, df) -> None:
    key = (symbol, curr_date)
    with _WRAPPED_CACHE_LOCK:
        _WRAPPED_CACHE[key] = df
        _WRAPPED_CACHE_ORDER.append(key)
        while len(_WRAPPED_CACHE_ORDER) > _WRAPPED_CACHE_MAX:
            evict = _WRAPPED_CACHE_ORDER.pop(0)
            _WRAPPED_CACHE.pop(evict, None)


def yf_retry(func, max_retries=3, base_delay=2.0):
    """Execute a yfinance call with exponential backoff on rate limits.

    yfinance raises YFRateLimitError on HTTP 429 responses but does not
    retry them internally. This wrapper adds retry logic specifically
    for rate limits. Other exceptions propagate immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except YFRateLimitError:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Yahoo Finance rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise
    # Defensive: loop must exit via return or raise. If we get here, surface
    # the bug rather than silently returning None (which would propagate as
    # a malformed DataFrame downstream).
    raise RuntimeError("yf_retry exited without returning or raising")


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse dates, drop invalid rows, fill price gaps."""
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])

    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=["Close"])
    data[price_cols] = data[price_cols].ffill().bfill()

    return data


def load_ohlcv(symbol: str, curr_date: str) -> pd.DataFrame:
    """Fetch OHLCV data with caching, filtered to prevent look-ahead bias.

    Downloads ~5 years of data up to today and stores one file per symbol.
    The cache file is reused across calls and refreshed when older than
    _CACHE_TTL_SECONDS.  Rows after curr_date are filtered out so backtests
    never see future prices.
    """
    # Reject ticker values that would escape the cache directory when
    # interpolated into the cache filename (e.g. ``../../tmp/x``).
    safe_symbol = safe_ticker_component(symbol)

    config = get_config()
    curr_date_dt = pd.to_datetime(curr_date)

    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today_date.strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    # Stable filename per symbol (no embedded dates) so the cache is reused
    # across calendar days. Refreshed by mtime, not by name.
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{safe_symbol}-YFin-data.csv",
    )

    needs_refresh = (
        not os.path.exists(data_file)
        or (time.time() - os.path.getmtime(data_file)) > _CACHE_TTL_SECONDS
    )

    if needs_refresh:
        data = yf_retry(lambda: yf.download(
            symbol,
            start=start_str,
            end=end_str,
            multi_level_index=False,
            progress=False,
            auto_adjust=True,
        ))
        data = data.reset_index()
        data.to_csv(data_file, index=False, encoding="utf-8")
    else:
        data = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")

    data = _clean_dataframe(data)

    # Filter to curr_date to prevent look-ahead bias in backtesting
    data = data[data["Date"] <= curr_date_dt]

    return data


def get_wrapped_stockstats(symbol: str, curr_date: str):
    """Return a stockstats-wrapped DataFrame for (symbol, curr_date), cached.

    The wrapped frame mutates in place as new indicators are accessed
    (stockstats appends a column for each indicator computed). We return
    the same cached object so subsequent indicator lookups for the same
    (symbol, curr_date) pair reuse already-computed columns.
    """
    cached = _wrapped_cache_get(symbol, curr_date)
    if cached is not None:
        return cached
    data = load_ohlcv(symbol, curr_date)
    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    _wrapped_cache_put(symbol, curr_date, df)
    return df


def filter_financials_by_date(data: pd.DataFrame, curr_date: str) -> pd.DataFrame:
    """Drop financial statement columns (fiscal period timestamps) after curr_date.

    yfinance financial statements use fiscal period end dates as columns.
    Columns after curr_date represent future data and are removed to
    prevent look-ahead bias.
    """
    if not curr_date or data.empty:
        return data
    cutoff = pd.Timestamp(curr_date)
    mask = pd.to_datetime(data.columns, errors="coerce") <= cutoff
    return data.loc[:, mask]


class StockstatsUtils:
    @staticmethod
    def get_stock_stats(
        symbol: Annotated[str, "ticker symbol for the company"],
        indicator: Annotated[
            str, "quantitative indicators based off of the stock data for the company"
        ],
        curr_date: Annotated[
            str, "curr date for retrieving stock price data, YYYY-mm-dd"
        ],
    ):
        df = get_wrapped_stockstats(symbol, curr_date)
        curr_date_str = pd.to_datetime(curr_date).strftime("%Y-%m-%d")

        df[indicator]  # trigger stockstats to calculate the indicator
        matching_rows = df[df["Date"].str.startswith(curr_date_str)]

        if not matching_rows.empty:
            indicator_value = matching_rows[indicator].values[0]
            return indicator_value
        else:
            return "N/A: Not a trading day (weekend or holiday)"
