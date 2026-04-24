import logging
import os
import re
import time
from typing import Annotated, Any, Callable

import pandas as pd
import yfinance as yf
from stockstats import wrap
from yfinance.exceptions import YFRateLimitError

from tradingagents.default_config import DEFAULT_CONFIG

from .config import get_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public exception — lets callers catch stockstats/yfinance failures by type
# ---------------------------------------------------------------------------


class YFinanceError(Exception):
    """Raised when yfinance or stockstats data fetching/processing fails."""
    pass


def safe_yf_download(
    tickers: str | list[str],
    start: str | None = None,
    end: str | None = None,
    **kwargs: Any,
) -> pd.DataFrame:
    """Central yf.download wrapper — enforces thread-safety and column hygiene.

    Defaults threads=False (safe inside LangGraph's thread pool) and
    multi_level_index=False (prevents duplicate-ticker column contamination).
    Callers may override either default by passing explicit keyword arguments.
    """
    kwargs.setdefault("threads", False)
    kwargs.setdefault("multi_level_index", False)
    return yf.download(tickers, start=start, end=end, **kwargs)


def _has_contaminated_columns(df: pd.DataFrame) -> bool:
    """Return True if any column name ends with .N (multi-ticker contamination)."""
    return any(
        bool(re.search(r"\.\d+$", str(col)))
        for col in df.columns
    )


def _assert_sufficient_rows(df: pd.DataFrame, min_rows: int, ticker: str) -> None:
    """Raise RuntimeError if df has fewer rows than the minimum required."""
    if len(df) < min_rows:
        raise RuntimeError(
            f"[OHLCV] Insufficient data for {ticker}: "
            f"need {min_rows} rows, got {len(df)}"
        )


def _is_close_plausible(df: pd.DataFrame, ticker: str) -> bool:
    """Return False if the 50-day rolling mean of Close deviates too far from the last close.

    Catches cross-ticker contamination where a high-priced ticker's data was
    mixed into a low-priced ticker's cache (e.g. TSM $170 in STM's $36 file).
    """
    close_col = "Close" if "Close" in df.columns else "close"
    if close_col not in df.columns:
        return True
    closes = pd.to_numeric(df[close_col], errors="coerce").dropna()
    if len(closes) < 10:
        return True
    last_close = closes.iloc[-1]
    rolling_mean = closes.tail(50).mean()
    if last_close <= 0 or rolling_mean <= 0:
        logger.warning("[OHLCV] %s: non-positive close value detected (last=%.2f, mean=%.2f)", ticker, last_close, rolling_mean)
        return False
    threshold = DEFAULT_CONFIG.get("ohlcv_sma_plausibility_threshold") or 3.0
    ratio = max(last_close, rolling_mean) / min(last_close, rolling_mean)
    if ratio > threshold:
        logger.warning(
            "[OHLCV] Plausibility check failed for %s: last_close=%.2f, rolling_mean_50=%.2f, ratio=%.2f > %.1f",
            ticker, last_close, rolling_mean, ratio, threshold,
        )
        return False
    return True


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
            elif _has_contaminated_columns(data):
                logger.warning(
                    "Cache file for %s has contaminated columns %s — deleting and re-fetching.",
                    symbol, [c for c in data.columns if re.search(r"\.\d+$", str(c))],
                )
                os.remove(data_file)
                data = None
            else:
                # Layer 6: staleness check
                date_col = "Date" if "Date" in data.columns else "date"
                if date_col in data.columns:
                    try:
                        last_date = pd.to_datetime(data[date_col]).max()
                        max_age = int(
                            get_config().get("ohlcv_cache_max_age_days")
                            or DEFAULT_CONFIG.get("ohlcv_cache_max_age_days")
                            or 2
                        )
                        if (pd.Timestamp.today() - last_date).days > max_age:
                            logger.warning(
                                "Cache file for %s is stale (last date %s, age %d days > %d) — re-fetching.",
                                symbol, last_date.date(), (pd.Timestamp.today() - last_date).days, max_age,
                            )
                            os.remove(data_file)
                            data = None
                    except Exception as exc:
                        logger.warning("Could not parse dates from cache for %s (%s) — re-fetching.", symbol, exc)
                        os.remove(data_file)
                        data = None
    else:
        data = None

    # ── Download from yfinance if cache miss / corrupt (with plausibility retry) ──
    _MAX_PLAUSIBILITY_RETRIES = 3
    for _attempt in range(_MAX_PLAUSIBILITY_RETRIES):
        if data is None:
            raw = safe_yf_download(
                symbol,
                start=start_date_str,
                end=end_date_str,
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
            logger.debug("Downloaded and cached OHLCV for %s → %s (attempt %d)", symbol, data_file, _attempt + 1)

        if not _is_close_plausible(data, symbol):
            if os.path.exists(data_file):
                os.remove(data_file)
            data = None
            if _attempt == _MAX_PLAUSIBILITY_RETRIES - 1:
                raise RuntimeError(
                    f"[OHLCV] Plausibility check failed for {symbol} after "
                    f"{_MAX_PLAUSIBILITY_RETRIES} attempts — possible persistent data "
                    f"contamination. Delete data_cache/ and retry."
                )
            logger.warning("[OHLCV] Plausibility failure for %s on attempt %d — retrying.", symbol, _attempt + 1)
            continue
        break

    _assert_sufficient_rows(data, min_rows=50, ticker=symbol)
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def yf_retry(func: Callable[..., Any], max_retries: int = 3, base_delay: float = 2.0) -> Any:
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
    ) -> str:
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
