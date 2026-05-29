import time
import logging

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError
from stockstats import wrap
from typing import Annotated
import os
from .config import get_config

logger = logging.getLogger(__name__)


def _is_empty_result(result) -> bool:
    """True for results yfinance returns when it is throttled rather than erroring."""
    if result is None:
        return True
    if isinstance(result, pd.DataFrame):
        return result.empty
    if isinstance(result, (list, tuple)):
        return len(result) == 0
    return False


def yf_retry(func, max_retries=3, base_delay=2.0, retry_on_empty=False):
    """Execute a yfinance call with exponential backoff on rate limits.

    yfinance raises YFRateLimitError on HTTP 429 responses but does not
    retry them internally. This wrapper adds retry logic specifically
    for rate limits. Other exceptions propagate immediately.

    When ``retry_on_empty`` is True, an empty result (None, empty
    tuple/list, or empty DataFrame) is also retried with backoff. Yahoo's
    options endpoint in particular tends to return an empty tuple instead
    of raising when throttled, so retrying recovers transient failures
    that would otherwise look like "no data". The empty result is still
    returned after the final attempt so callers can distinguish a genuine
    empty from a hard error.
    """
    for attempt in range(max_retries + 1):
        try:
            result = func()
        except YFRateLimitError:
            if attempt >= max_retries:
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Yahoo Finance rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(delay)
            continue

        if retry_on_empty and _is_empty_result(result) and attempt < max_retries:
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Yahoo Finance returned empty result, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(delay)
            continue

        return result


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame without backfilling from future rows."""
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])

    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=["Close"])
    data[price_cols] = data[price_cols].ffill()
    data = data.dropna(subset=price_cols)

    return data


def load_ohlcv(symbol: str, curr_date: str) -> pd.DataFrame:
    """Fetch OHLCV data with caching, filtered to prevent look-ahead bias.

    Downloads 5 years of data and caches per symbol. The cache is reused
    when (a) it already covers curr_date, or (b) it was refreshed within
    LIVE_CACHE_TTL_SECONDS. Rows after curr_date are filtered out so
    backtests never see future prices, but live runs that ask for today
    will trigger a refresh after the TTL expires so today's bar is picked
    up once yfinance publishes it (typically right after the US close).
    """
    config = get_config()
    curr_date_dt = pd.to_datetime(curr_date).normalize()

    today_date = pd.Timestamp.today().normalize()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    cache_end_str = today_date.strftime("%Y-%m-%d")
    # yfinance treats `end` as exclusive, so push it one day past today to
    # actually include today's daily bar once it is published.
    fetch_end_str = (today_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{symbol}-YFin-data-{start_str}-{cache_end_str}.csv",
    )

    LIVE_CACHE_TTL_SECONDS = 2 * 60 * 60  # 2h: bound refetch frequency on weekends/holidays

    needs_fetch = not os.path.exists(data_file)
    data = None
    if not needs_fetch:
        try:
            data = pd.read_csv(data_file, on_bad_lines="skip")
            cached = _clean_dataframe(data)
            cached_max = cached["Date"].max() if not cached.empty else pd.NaT
            age_seconds = time.time() - os.path.getmtime(data_file)
            stale = (
                pd.isna(cached_max)
                or (cached_max < curr_date_dt and age_seconds > LIVE_CACHE_TTL_SECONDS)
            )
            if stale:
                needs_fetch = True
        except Exception:
            needs_fetch = True

    if needs_fetch:
        data = yf_retry(lambda: yf.download(
            symbol,
            start=start_str,
            end=fetch_end_str,
            multi_level_index=False,
            progress=False,
            auto_adjust=True,
        ))
        data = data.reset_index()
        data.to_csv(data_file, index=False)

    data = _clean_dataframe(data)

    # Filter to curr_date to prevent look-ahead bias in backtesting
    data = data[data["Date"] <= curr_date_dt]

    return data


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
        data = load_ohlcv(symbol, curr_date)
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        curr_date_str = pd.to_datetime(curr_date).strftime("%Y-%m-%d")

        df[indicator]  # trigger stockstats to calculate the indicator
        matching_rows = df[df["Date"].str.startswith(curr_date_str)]

        if not matching_rows.empty:
            indicator_value = matching_rows[indicator].values[0]
            return indicator_value
        else:
            return "N/A: Not a trading day (weekend or holiday)"
