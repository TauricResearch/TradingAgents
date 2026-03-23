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

# ---------------------------------------------------------------------------
# Public exception — lets callers catch stockstats/yfinance failures by type
# ---------------------------------------------------------------------------


class YFinanceError(Exception):
    """Raised when yfinance or stockstats data fetching/processing fails."""
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse dates, drop invalid rows, fill price gaps.
    Ensure DataFrame has lowercase columns for stockstats."""
    df = data.copy()
    df.columns = [str(c).lower() for c in df.columns]

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])

    price_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    if price_cols:
        df[price_cols] = df[price_cols].apply(pd.to_numeric, errors="coerce")

    if "close" in df.columns:
        df = df.dropna(subset=["close"])

    if price_cols:
        df[price_cols] = df[price_cols].ffill().bfill()

    return df


def _load_or_fetch_ohlcv(symbol: str) -> pd.DataFrame:
    """Single authority for loading OHLCV data: cache → yfinance download → normalize.

    Cache filename is always derived from today's date (15-year window) so the
    cache key never goes stale.  If a cached file exists but is corrupt (too few
    rows to be useful), it is deleted and re-fetched rather than silently
    returning bad data.

    Raises:
        YFinanceError: if the download returns an empty DataFrame or fails.
    """
    config = get_config()

    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=15)
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = today_date.strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)

    data_file = os.path.join(
        config["data_cache_dir"],
        f"{symbol}-YFin-data-{start_date_str}-{end_date_str}.csv",
    )

    # ── Try to load from cache ────────────────────────────────────────────────
    if os.path.exists(data_file):
        try:
            data = pd.read_csv(data_file)  # no on_bad_lines="skip" — we want to know about corruption
        except Exception as exc:
            logger.warning(
                "Corrupt cache file for %s (%s) — deleting and re-fetching.", symbol, exc
            )
            os.remove(data_file)
            data = None
        else:
            # Validate: a 15-year daily file should have well over 100 rows
            if len(data) < 50:
                logger.warning(
                    "Cache file for %s has only %d rows — likely truncated, re-fetching.",
                    symbol, len(data),
                )
                os.remove(data_file)
                data = None
    else:
        data = None

    # ── Download from yfinance if cache miss / corrupt ────────────────────────
    if data is None:
        raw = yf.download(
            symbol,
            start=start_date_str,
            end=end_date_str,
            multi_level_index=False,
            progress=False,
            auto_adjust=True,
        )
        if raw.empty:
            raise YFinanceError(
                f"yfinance returned no data for symbol '{symbol}' "
                f"({start_date_str} → {end_date_str})"
            )
        data = raw.reset_index()
        data.to_csv(data_file, index=False)
        logger.debug("Downloaded and cached OHLCV for %s → %s", symbol, data_file)

    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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
        curr_date_dt = pd.to_datetime(curr_date)
        curr_date_str = curr_date_dt.strftime("%Y-%m-%d")

        data = _load_or_fetch_ohlcv(symbol)
        data = _clean_dataframe(data)
        df = wrap(data)
        # After wrap(), the date column becomes the datetime index (named 'date').
        # Access via df.index, not df["Date"] which stockstats would try to parse as an indicator.

        df[indicator]  # trigger stockstats to calculate the indicator
        date_index_strs = df.index.strftime("%Y-%m-%d")
        matching_rows = df[date_index_strs == curr_date_str]

        if not matching_rows.empty:
            return matching_rows[indicator].values[0]
        else:
            return "N/A: Not a trading day (weekend or holiday)"
