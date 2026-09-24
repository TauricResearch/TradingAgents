import logging
import os
import time

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import NoMarketDataError, VendorRateLimitError
from tradingagents.dataflows.net import vendor_reachable
from tradingagents.dataflows.symbols import normalize_symbol, safe_ticker_component

logger = logging.getLogger(__name__)

YAHOO_HOST = "https://query2.finance.yahoo.com"

# A vendor's latest OHLCV row this many calendar days before the requested date
# is treated as stale. Generous enough to span long holiday weekends, tight
# enough to catch the year-old frames yfinance occasionally returns (#1021).
MAX_OHLCV_STALE_DAYS = 10

# How long a same-day cache that does not yet reach the requested day may be
# reused before it is refetched (#1150). Short enough that an intraday run picks
# up today's close soon after it publishes, long enough that a day with no bar
# at all (weekend, holiday) cannot trigger a download on every call.
OHLCV_CACHE_TTL_SECONDS = 900


def raise_for_empty(symbol: str, canonical: str, what: str) -> None:
    """Report an empty Yahoo result as an absence, or as an outage if it is one.

    yfinance returns an empty frame for a failed request rather than raising, so
    without this a Yahoo outage reads as "this symbol has no {what}".
    """
    if not vendor_reachable(YAHOO_HOST):
        raise VendorRateLimitError(f"Yahoo Finance is unreachable; no {what} was retrieved")
    raise NoMarketDataError(symbol, canonical, f"no {what}")


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


def _ensure_date_column(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize the date column to ``Date``.

    Some yfinance builds leave the index unnamed (so ``reset_index()`` yields
    ``index``) or use ``Datetime`` for intraday data. Rename the first
    date-like column so indicators don't silently drop when it isn't ``Date``.
    """
    if "Date" in data.columns:
        return data
    for candidate in ("index", "Datetime", "date"):
        if candidate in data.columns:
            return data.rename(columns={candidate: "Date"})
    return data


def _local_midnight(value) -> pd.Timestamp:
    """A single timestamp as its naive, midnight-normalized local date (or NaT)."""
    if pd.isna(value):
        return pd.NaT
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return pd.NaT
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)  # drop tz, keep the local wall-clock date
    return ts.normalize()


def _normalize_dates(dates) -> pd.Series:
    """Parse to naive, midnight-normalized dates so tz-aware or intraday
    timestamps compare correctly against the naive ``curr_date`` cutoff (#1201).

    Normalized per element: 5 years of yfinance bars span daylight-saving
    changes (and cache CSVs round-trip the offsets as strings), so the series can
    carry mixed UTC offsets that ``pd.to_datetime`` cannot unify without
    ``utc=True`` — which would shift non-US (positive-offset) markets to the
    previous day. Keeping each bar's own local date avoids both.
    """
    return pd.to_datetime(pd.Series(dates).map(_local_midnight))


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse/normalize dates and
    coerce prices to numeric (NaN where invalid). Dropping incomplete rows and
    filling gaps is left to ``_fill_price_gaps`` so the caller can first inspect
    the latest in-range bar (#1201)."""
    data = _ensure_date_column(data)
    data["Date"] = _normalize_dates(data["Date"])
    data = data.dropna(subset=["Date"]).copy()

    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    return data


def _fill_price_gaps(data: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with no close and forward/back-fill remaining price gaps so
    indicators compute on a continuous series."""
    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    # copy() so a filtered (sliced) input is written to safely, not via a view.
    data = data.dropna(subset=["Close"]).copy()
    data[price_cols] = data[price_cols].ffill().bfill()
    return data


def _coerce_ohlcv_dates(data: pd.DataFrame) -> pd.Series:
    """Return parsed dates from an OHLCV frame, whether Date is a column or the index."""
    if "Date" in data.columns:
        return pd.to_datetime(data["Date"], errors="coerce").dropna()
    # yfinance keeps the dates in the index (a DatetimeIndex, sometimes unnamed).
    if isinstance(data.index, pd.DatetimeIndex):
        return pd.Series(pd.to_datetime(data.index, errors="coerce")).dropna()
    # Fallback: expose the index and look for any date-like column.
    df = data.reset_index()
    for col in ("Date", "Datetime", "date", "index"):
        if col in df.columns:
            parsed = pd.to_datetime(df[col], errors="coerce").dropna()
            if not parsed.empty:
                return parsed
    return pd.Series(dtype="datetime64[ns]")


def _assert_ohlcv_not_stale(
    data: pd.DataFrame,
    curr_date: str,
    symbol: str,
    canonical: str | None = None,
    *,
    max_stale_days: int = MAX_OHLCV_STALE_DAYS,
) -> None:
    """Reject OHLCV whose latest row is far older than curr_date.

    Raises NoMarketDataError (with a stale-specific detail) so the router treats
    it like any other "no usable data from this vendor" — try the next vendor,
    then emit one clear unavailable signal. Empty frames are left to the
    caller's existing no-data handling; this guards only the dangerous case of
    present-but-stale rows (a vendor returning a year-old frame that would
    otherwise feed wrong prices to the agent, #1021).
    """
    if data is None or data.empty:
        return
    requested = pd.to_datetime(curr_date, errors="coerce")
    if pd.isna(requested):
        return
    requested = requested.normalize()
    dates = _coerce_ohlcv_dates(data)
    if dates.empty:
        return
    latest = dates.max().normalize()
    stale_days = (requested - latest).days
    if stale_days > max_stale_days:
        raise NoMarketDataError(
            symbol,
            canonical,
            f"latest row is {latest.date()}, {stale_days} days before the "
            f"requested {requested.date()} (stale) — refusing to use it",
        )


def _cache_is_fresh(data_file, curr_date_dt, now) -> bool:
    """Whether the symbol's cached download can serve this request.

    The file holds the download made on the day it was written, so it serves
    only that day. A current-day request also refetches once the file is older
    than the TTL: Yahoo publishes a partial daily candle during market hours,
    whose ``Close`` is not the closing price, and row inspection cannot tell it
    from a final one (#1150).
    """
    written = pd.Timestamp.fromtimestamp(os.path.getmtime(data_file))
    if written.date() != now.date():
        return False
    return curr_date_dt.date() < now.date() or (now - written).total_seconds() <= OHLCV_CACHE_TTL_SECONDS


def load_ohlcv(symbol: str, curr_date: str, fill_gaps: bool = True) -> pd.DataFrame:
    """Fetch OHLCV data with caching, filtered to prevent look-ahead bias.

    Downloads 5 years of data up to today and caches per symbol. On
    subsequent calls the cache is reused. Rows after curr_date are
    filtered out so backtests never see future prices.

    ``fill_gaps`` carries prices forward over gaps so indicators compute on a
    continuous series. Pass ``False`` to read the values as the vendor reported
    them, leaving a cell that was never reported empty.
    """
    # Resolve broker/forex symbols (XAUUSD+ -> GC=F) to Yahoo's convention,
    # then reject values that would escape the cache directory when
    # interpolated into the cache filename (e.g. ``../../tmp/x``).
    canonical = normalize_symbol(symbol)
    safe_symbol = safe_ticker_component(canonical)

    config = get_config()
    curr_date_dt = pd.to_datetime(curr_date).normalize()

    # One cache file per symbol, holding the latest 5y-to-today download.
    now = pd.Timestamp.today()
    start_date = now - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    # yfinance ``end`` is EXCLUSIVE; request tomorrow so today's row is included
    # when curr_date is the current day (#986). Look-ahead is still prevented by
    # the curr_date filter below.
    end_str = (now + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{safe_symbol}-YFin-data.csv",
    )

    # A cached file may be empty if a prior fetch failed (unknown symbol,
    # transient rate limit). Treat an empty/columnless cache as a miss and
    # re-fetch rather than serving the poisoned file forever.
    data = None
    if os.path.exists(data_file):
        cached = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
        if (
            not cached.empty
            and "Close" in cached.columns
            and _cache_is_fresh(data_file, curr_date_dt, now)
        ):
            data = cached

    if data is None:
        downloaded = yf_retry(lambda: yf.download(
            canonical,
            start=start_str,
            end=end_str,
            multi_level_index=False,
            progress=False,
            auto_adjust=True,
        ))
        downloaded = _ensure_date_column(downloaded.reset_index())
        # Only cache real data — never persist an empty frame.
        if downloaded.empty or "Close" not in downloaded.columns:
            raise_for_empty(symbol, canonical, "price rows")
        downloaded.to_csv(data_file, index=False, encoding="utf-8")
        data = downloaded

    data = _clean_dataframe(data)

    # Filter to curr_date to prevent look-ahead bias in backtesting.
    data = data[data["Date"] <= curr_date_dt]

    # A closeless newest bar is an unsettled session, not a symbol without data.
    # _fill_price_gaps below drops it, here and mid-series alike, so the frame
    # ends at the last settled bar; only a range with no close anywhere is no
    # data (#1201, #1289).
    if not data.empty and pd.isna(data["Close"].iloc[-1]):
        settled = data["Close"].notna().to_numpy().nonzero()[0]
        if settled.size == 0:
            raise NoMarketDataError(
                symbol, canonical, "no bar in range has a closing price"
            )
        logger.warning(
            "%s: %d trailing bar(s) through %s have no closing price; using %s "
            "as the latest close.", canonical, len(data) - settled[-1] - 1,
            data["Date"].iloc[-1].date(), data["Date"].iloc[settled[-1]].date(),
        )

    # Indicators need a continuous series, so gaps are carried forward. A caller
    # that reports the numbers themselves asks for the frame as it was reported:
    # a filled cell is the previous session's price under this session's date.
    data = _fill_price_gaps(data) if fill_gaps else data.dropna(subset=["Close"]).copy()

    # Reject a stale frame (latest row far older than curr_date) rather than
    # feeding year-old prices into indicators (#1021).
    _assert_ohlcv_not_stale(data, curr_date, symbol, canonical)

    return data


