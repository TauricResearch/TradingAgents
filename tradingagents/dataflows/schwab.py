"""Schwab Market Data vendor: OHLCV (``get_schwab_stock``) and technical
indicators (``get_schwab_indicators``) for US equities/ETFs.

Opt-in only. The router falls back to yfinance whenever this vendor raises
``SchwabNotConfiguredError`` (not installed / no token) or ``NoMarketDataError``
(non-whitelisted symbol, 404, empty candles, stale data).

Design invariants (see the plan):

- **Symbol whitelist ``^[A-Z]{1,5}$``.** Only plain-letter common stock / ETF
  symbols go to Schwab. Anything with ``.`` / ``-`` / ``=`` / ``^`` / crypto
  (e.g. ``BRK.B``, ``BRK-A``, ``BTC-USD``, ``^GSPC``, ``EURUSD=X``) raises
  ``NoMarketDataError`` immediately and never reaches Schwab, because those
  broker/Yahoo formats are not Schwab's convention (Schwab uses ``/`` for
  class/preferred shares) and yfinance handles them better.
- **Explicit ``get_price_history(period=FIVE_YEARS, DAILY)``**, never
  ``get_price_history_every_day`` (which forces a 1971->today full-history pull).
- **Disk cache** (per-symbol CSV under ``data_cache_dir``, historical rows reused
  forever, current-day rows refreshed after a short TTL), shared by both the
  OHLCV and indicator paths via ``_fetch_schwab_daily``.
- **No ``resp.raise_for_status()``.** schwab-py returns raw httpx responses; we
  classify on ``resp.status_code`` (raise_for_status would throw an httpx error
  that bypasses this classification).
- **Look-ahead trimming** converts dates with ``pd.to_datetime`` before
  comparing against the datetime64 ``Date`` column (never string-vs-datetime64).
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from typing import Annotated

import pandas as pd

from .config import get_config
from .errors import NoMarketDataError
from .schwab_common import (
    SchwabNotConfiguredError,
    SchwabRateLimitError,
    candles_to_ohlcv_df,
    get_client,
)
from .stockstats_utils import (
    _assert_ohlcv_not_stale,
    _clean_dataframe,
    render_indicator_window,
)
from .symbol_utils import normalize_symbol
from .utils import safe_ticker_component

# Only plain-letter US common stock / ETF symbols are eligible for Schwab.
_SCHWAB_SYMBOL_WHITELIST = re.compile(r"^[A-Z]{1,5}$")

# Reuse the same current-day cache TTL semantics as the yfinance OHLCV cache so
# an intraday run picks up today's close soon after it publishes while a weekend
# / holiday with no new bar cannot trigger a refetch on every call.
SCHWAB_CACHE_TTL_SECONDS = 900


def _needs_same_day_refresh(
    data_file: str, curr_date_dt: pd.Timestamp, today_date: pd.Timestamp
) -> bool:
    """Whether a per-symbol cache must be refetched for the requested as-of day.

    Mirrors the yfinance OHLCV cache semantics (``stockstats_utils.load_ohlcv``):
    a request whose as-of date is before today asks only for historical rows,
    which are immutable, so the cache is reused unconditionally (never subject to
    the TTL) — this is what lets a long backtest reuse one download instead of
    refetching per day. Only a current-day request can serve a stale in-progress
    or missing bar, so the TTL governs how often that current-day cache refreshes.
    """
    if curr_date_dt.date() < today_date.date():
        return False
    return time.time() - os.path.getmtime(data_file) > SCHWAB_CACHE_TTL_SECONDS


def _fetch_schwab_daily(canonical: str, as_of_date: str) -> pd.DataFrame:
    """Fetch (and disk-cache) 5 years of daily OHLCV for a whitelisted symbol.

    Shared by ``get_schwab_stock`` and ``get_schwab_indicators`` so the same
    ticker is pulled at most once per TTL window. Returns the full (untrimmed,
    unfiltered) tz-naive OHLCV frame; callers do their own look-ahead trimming
    and (indicator path only) cleaning.

    ``as_of_date`` (the caller's ``end_date`` / ``curr_date``) decides cache
    reuse: a historical as-of date reuses the cache forever, while a current-day
    as-of date honours the short TTL so today's still-forming bar is refreshed.

    Status-code classification (schwab-py never raises on non-200):
      - 200 -> parse candles
      - 401 -> SchwabNotConfiguredError (auth broken -> fall back)
      - 429 -> SchwabRateLimitError (router skips to next vendor)
      - 404 / empty candles -> NoMarketDataError (unknown/uncovered symbol)
      - 5xx / other -> Exception (loud; router records it, then falls back)
    """
    safe_symbol = safe_ticker_component(canonical)
    config = get_config()
    today_date = pd.Timestamp.today()
    curr_date_dt = pd.to_datetime(as_of_date)

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"], f"{safe_symbol}-Schwab-daily.csv"
    )

    if os.path.exists(data_file) and not _needs_same_day_refresh(
        data_file, curr_date_dt, today_date
    ):
        cached = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
        # Serve the cache only when it carries the full title-case OHLCV schema;
        # a truncated or externally-corrupted file is treated as a miss and
        # refetched rather than fed (partially) to stockstats.
        required_cols = {"Date", "Open", "High", "Low", "Close", "Volume"}
        if not cached.empty and required_cols.issubset(cached.columns):
            cached["Date"] = pd.to_datetime(cached["Date"], errors="coerce")
            cached = cached.dropna(subset=["Date"])
            return cached

    client = get_client()

    # Explicit 5-year daily window (aligns with the yfinance load_ohlcv cache
    # window); never the convenience get_price_history_every_day (1971->today).
    # ``frequency=Frequency.DAILY`` sends the wire value 1 (candles per day) — in
    # schwab-py the Frequency enum aliases DAILY onto value 1, matching schwab-py's
    # own daily examples — so we pass it explicitly rather than relying on the
    # server defaulting an omitted frequency.
    ph = client.PriceHistory
    resp = client.get_price_history(
        canonical,
        period_type=ph.PeriodType.YEAR,
        period=ph.Period.FIVE_YEARS,
        frequency_type=ph.FrequencyType.DAILY,
        frequency=ph.Frequency.DAILY,
    )

    # Classify on status_code; NEVER call resp.raise_for_status() (it would
    # throw an httpx.HTTPStatusError that bypasses this classification).
    status = resp.status_code
    if status == 401:
        raise SchwabNotConfiguredError(
            f"Schwab returned 401 for {canonical!r}; the token is invalid or "
            "expired. Refresh it via your schwab-py login."
        )
    if status == 429:
        raise SchwabRateLimitError(
            f"Schwab rate limit hit fetching {canonical!r} (HTTP 429)."
        )
    if status == 404:
        raise NoMarketDataError(
            canonical, canonical, "Schwab returned 404 (symbol not found)"
        )
    if status != 200:
        raise Exception(
            f"Schwab price-history request for {canonical!r} failed with "
            f"HTTP {status}."
        )

    df = candles_to_ohlcv_df(resp.json())
    if df.empty:
        raise NoMarketDataError(
            canonical, canonical, "Schwab returned no candles"
        )

    # Persist the full window. Historical rows are immutable; the same-day TTL
    # above governs refresh of the current-day bar.
    df.to_csv(data_file, index=False, encoding="utf-8")
    return df


def get_schwab_stock(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Return Schwab daily OHLCV as a CSV string, matching the yfinance format.

    Signature mirrors ``get_YFin_data_online``. Non-whitelisted symbols and
    unknown/empty/stale symbols raise ``NoMarketDataError`` so the router falls
    back to yfinance (or emits a clean NO_DATA sentinel).

    The output is raw (unadjusted) price data: unlike yfinance's
    ``auto_adjust=True`` frame, Schwab prices are not back-adjusted for
    splits/dividends. Values are not cleaned (no ffill); only null-close rows are
    dropped in ``candles_to_ohlcv_df``.
    """
    # Validate the date inputs the same way the yfinance vendor does.
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    canonical = normalize_symbol(symbol)
    if not _SCHWAB_SYMBOL_WHITELIST.fullmatch(canonical):
        # Class/preferred/crypto/index/forex symbols are not Schwab's convention
        # (or yfinance covers them better) -> let another vendor handle it.
        raise NoMarketDataError(
            symbol,
            canonical,
            "symbol is not a plain US equity/ETF ticker; Schwab vendor only "
            "handles ^[A-Z]{1,5}$",
        )

    df = _fetch_schwab_daily(canonical, end_date)

    # Look-ahead trim: convert to Timestamp before comparing against the
    # datetime64 Date column (never string-vs-datetime64). The <= end bound
    # prevents future rows leaking into a backtest. This is the alpha_vantage
    # _filter_csv_by_date_range precedent, not yfinance load_ohlcv.
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    # .copy() so the later in-place round() writes to an owned frame, not a view
    # of the cached frame (avoids pandas' SettingWithCopyWarning).
    df = df[(df["Date"] >= start_dt) & (df["Date"] <= end_dt)].copy()

    if df.empty:
        raise NoMarketDataError(
            symbol, canonical, f"no rows between {start_date} and {end_date}"
        )

    # Reject a stale frame (latest row far older than end_date) before it is
    # formatted into the report.
    _assert_ohlcv_not_stale(df, end_date, symbol, canonical)

    # Round for cleaner display; guard each column so a missing one (Schwab has
    # no Adj Close) is skipped without KeyError.
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    # If the earliest available bar is later than the requested start, flag it so
    # the agent does not treat a partial window as complete history.
    actual_start = df["Date"].min()
    partial_note = ""
    if pd.notna(actual_start) and actual_start > start_dt:
        partial_note = (
            f"# Note: earliest available Schwab bar is "
            f"{actual_start.strftime('%Y-%m-%d')} (later than requested "
            f"{start_date}); window is partial.\n"
        )

    csv_string = df.set_index("Date").to_csv()

    label = canonical if canonical == symbol.upper() else f"{canonical} (from {symbol})"
    header = f"# Stock data for {label} from {start_date} to {end_date} (Schwab)\n"
    header += f"# Total records: {len(df)}\n"
    header += partial_note
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


def get_schwab_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Return a Schwab-sourced technical-indicator window, matching the yfinance
    tool's output shape.

    Fetch (shared disk cache) -> look-ahead trim (``<= curr_date``) -> clean
    (indicator path is the ONLY place cleaning/ffill happens) -> render. Unlike
    the yfinance path there is no per-day fallback (no second fetch source); a
    failure is left to the router to fall back to yfinance.
    """
    canonical = normalize_symbol(symbol)
    if not _SCHWAB_SYMBOL_WHITELIST.fullmatch(canonical):
        raise NoMarketDataError(
            symbol,
            canonical,
            "symbol is not a plain US equity/ETF ticker; Schwab vendor only "
            "handles ^[A-Z]{1,5}$",
        )

    df = _fetch_schwab_daily(canonical, curr_date)

    # Look-ahead trim (convert curr_date to Timestamp before comparing).
    curr_dt = pd.to_datetime(curr_date)
    df = df[df["Date"] <= curr_dt]

    if df.empty:
        raise NoMarketDataError(
            symbol, canonical, f"no Schwab rows on or before {curr_date}"
        )

    # Reject a stale frame (latest row far older than curr_date) before it feeds
    # indicators, mirroring the OHLCV path and yfinance's load_ohlcv guard: a
    # present-but-year-old frame would otherwise compute misleading indicators.
    _assert_ohlcv_not_stale(df, curr_date, symbol, canonical)

    # Cleaning (ffill/bfill/coerce) happens ONLY on the indicator path, never on
    # the OHLCV path.
    cleaned = _clean_dataframe(df)
    return render_indicator_window(cleaned, indicator, curr_date, look_back_days)
