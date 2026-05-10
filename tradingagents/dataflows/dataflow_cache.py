"""Cross-ticker on-disk cache for slow-changing dataflow results.

Two access patterns this layer accelerates:
  1. **Same day, multiple tickers** — global / macro news is identical for
     every ticker analysed on the same calendar day. Cache by date alone.
  2. **Same ticker, different days within a quarter** — financial statements
     and the fundamentals overview only roll forward when a new quarterly
     report is filed. Cache by (ticker, fiscal_quarter_end).

This is distinct from the per-(ticker, trade_date) analyst report cache:
that one short-circuits the whole analyst, whereas this one short-circuits
individual data fetches and so still benefits a fresh run on a new
(ticker, date) pair.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from .config import get_config

logger = logging.getLogger(__name__)

# Methods we cache here. Each entry maps to a key-builder defined below.
_CACHEABLE_METHODS = frozenset({
    "get_global_news",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
})


def _cache_dir() -> str:
    return os.path.join(get_config()["data_cache_dir"], "dataflow_cache")


def _path_for(key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return os.path.join(_cache_dir(), f"{digest}.txt")


def _read(key: str) -> Optional[str]:
    path = _path_for(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        logger.warning("dataflow cache read failed for %s: %s", key, e)
        return None


def _write(key: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        return
    try:
        os.makedirs(_cache_dir(), exist_ok=True)
        with open(_path_for(key), "w", encoding="utf-8") as f:
            f.write(value)
    except OSError as e:
        logger.warning("dataflow cache write failed for %s: %s", key, e)


def fiscal_quarter_end(date_str: str) -> str:
    """Most recent calendar quarter end (Mar 31 / Jun 30 / Sep 30 / Dec 31) on
    or before ``date_str``. Used as a cache bucket so financial statements
    are fetched at most once per quarter per ticker.
    """
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    quarters = [(3, 31), (6, 30), (9, 30), (12, 31)]
    candidates = []
    for year in (d.year - 1, d.year):
        for m, day in quarters:
            qe = date(year, m, day)
            if qe <= d:
                candidates.append(qe)
    return max(candidates).isoformat()


def iso_week_monday(date_str: str) -> str:
    """Monday of the ISO week containing ``date_str``. Bucket for sources
    that change at most weekly (Cninfo regulatory filings).
    """
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def cache_key_for(method: str, args: tuple, kwargs: dict) -> Optional[str]:
    """Build a cache key for a vendor call, or return None if uncacheable.

    Returning None falls through to the live fetch with no caching, so a
    new method always works even before its key-builder is added.
    """
    try:
        if method == "get_global_news":
            curr_date = args[0] if args else kwargs.get("curr_date")
            lookback = args[1] if len(args) > 1 else kwargs.get("look_back_days", 7)
            limit = args[2] if len(args) > 2 else kwargs.get("limit", 5)
            if not curr_date:
                return None
            return f"global_news::{curr_date}::{lookback}::{limit}"

        if method == "get_fundamentals":
            ticker = args[0] if args else kwargs.get("ticker")
            curr_date = args[1] if len(args) > 1 else kwargs.get("curr_date")
            if not ticker or not curr_date:
                return None
            return f"fundamentals::{ticker}::{fiscal_quarter_end(curr_date)}"

        if method in ("get_balance_sheet", "get_cashflow", "get_income_statement"):
            ticker = args[0] if args else kwargs.get("ticker")
            freq = args[1] if len(args) > 1 else kwargs.get("freq", "quarterly")
            curr_date = args[2] if len(args) > 2 else kwargs.get("curr_date")
            if not ticker or not curr_date:
                return None
            return f"{method}::{ticker}::{freq}::{fiscal_quarter_end(curr_date)}"
    except (IndexError, ValueError, KeyError, TypeError) as e:
        logger.debug("dataflow cache key build failed for %s: %s", method, e)
        return None

    return None


def is_cacheable(method: str) -> bool:
    return method in _CACHEABLE_METHODS


def cached_call(method: str, args: tuple, kwargs: dict, fetch: Callable[[], object]) -> object:
    """Lookup-or-fetch, returning the (possibly cached) value.

    Falls through to ``fetch()`` when:
      - the method is not in the cacheable allowlist,
      - the key builder cannot derive a stable key,
      - the fetched value is not a string (we only cache strings here).
    """
    if not is_cacheable(method):
        return fetch()

    key = cache_key_for(method, args, kwargs)
    if key is None:
        return fetch()

    hit = _read(key)
    if hit is not None:
        return hit

    value = fetch()
    if isinstance(value, str):
        _write(key, value)
    return value


def vendor_cache_key(
    vendor: str, method: str, args: tuple, kwargs: dict
) -> Optional[str]:
    """Per-vendor cache key for the news methods.

    Each news vendor caches independently so the multi-source merge for
    HK / SH / SZ tickers reuses whatever is already hot. Bucketing:

    * Eastmoney / CLS / yfinance: daily — these surface fresh
      editorial / flash content on a daily cadence.
    * Cninfo: ISO-weekly — A-share regulatory filings move slowly enough
      that re-fetching daily is wasteful. A buyback-progress filing today
      doesn't materially change the disclosure list this week.
    """
    if method == "get_news":
        ticker = args[0] if args else kwargs.get("ticker")
        end_date = args[2] if len(args) > 2 else kwargs.get("end_date")
        if not ticker or not end_date:
            return None
        if vendor == "cninfo":
            return f"cninfo::{ticker}::{iso_week_monday(end_date)}"
        return f"{vendor}::news::{ticker}::{end_date}"
    if method == "get_insider_transactions":
        ticker = args[0] if args else kwargs.get("ticker")
        if not ticker:
            return None
        return f"{vendor}::insider::{ticker}::{date.today().isoformat()}"
    return None


def vendor_cached_call(
    vendor: str,
    method: str,
    args: tuple,
    kwargs: dict,
    fetch: Callable[[], object],
) -> object:
    """Try the per-vendor cache first; on miss, fetch and store.

    Falls through to ``fetch()`` when no stable key can be derived for
    this vendor/method combo (e.g. ``get_global_news`` is already cached
    by the legacy ``cached_call`` keyed on the date+window+limit triple,
    no per-vendor split needed).
    """
    key = vendor_cache_key(vendor, method, args, kwargs)
    if key is None:
        return fetch()

    hit = _read(key)
    if hit is not None:
        return hit

    value = fetch()
    if isinstance(value, str):
        # Skip-markers from a non-applicable vendor (e.g. Cninfo on an HK
        # ticker) are intentionally NOT cached — they're cheap to regenerate
        # and we don't want to lock them in if the user later configures a
        # different vendor mapping.
        stripped = value.strip()
        is_skip = stripped.startswith("[") and "skip" in stripped.lower() and stripped.endswith("]")
        if not is_skip:
            _write(key, value)
    return value


def clear_dataflow_cache() -> int:
    """Delete every cached dataflow file. Returns the count removed."""
    base = _cache_dir()
    if not os.path.isdir(base):
        return 0
    removed = 0
    for name in os.listdir(base):
        path = os.path.join(base, name)
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed
