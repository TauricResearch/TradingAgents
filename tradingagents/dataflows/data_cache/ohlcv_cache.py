"""OHLCV disk cache with incremental daily updates.

On the first call for a given ticker universe, downloads the full requested
period and saves it as a parquet file.  On subsequent calls during the same
day the cache is served from disk (zero network).  On the next calendar day
only the missing trading days are fetched and appended, keeping total download
volume proportional to *time elapsed* rather than universe size.

Cache files live in data/ohlcv_cache/ (configurable):
  {md5(sorted_tickers)[:12]}.parquet   — long-format OHLCV rows
  {md5(sorted_tickers)[:12]}.meta.json — {last_updated, tickers, period}
"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_CACHE_DIR = "data/ohlcv_cache"

# Keep at most this many rows per ticker to prevent unbounded growth (~2 years)
MAX_ROWS_PER_TICKER = 504

# Approximate trading days for each yfinance period string (used to slice
# a larger cached history down to the requested period on return).
PERIOD_TO_DAYS: Dict[str, Optional[int]] = {
    "1d": 1,
    "5d": 5,
    "1mo": 21,
    "3mo": 63,
    "6mo": 130,
    "1y": 252,
    "2y": 504,
    "5y": 1260,
    "max": None,  # return everything
}


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────


def _cache_key(tickers: List[str]) -> str:
    """Stable 12-char hash of the (sorted, uppercase) ticker set."""
    canonical = ",".join(sorted({t.upper() for t in tickers}))
    return hashlib.md5(canonical.encode()).hexdigest()[:12]


def _paths(cache_dir: str, key: str):
    base = Path(cache_dir)
    return base / f"{key}.parquet", base / f"{key}.meta.json"


def _read_meta(meta_path: Path) -> Optional[dict]:
    try:
        with open(meta_path) as f:
            return json.load(f)
    except Exception:
        return None


def _write_meta(meta_path: Path, data: dict) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w") as f:
        json.dump(data, f)


def _batch_download(tickers: List[str], **kwargs) -> pd.DataFrame:
    """Download via yf.download and return in long format.

    Long format columns: Date, Ticker, Open, High, Low, Close, Volume
    Date is stored as tz-naive datetime (normalised to midnight).
    """
    try:
        raw = yf.download(tickers, auto_adjust=True, progress=False, **kwargs)
    except Exception as e:
        logger.warning(f"yfinance download failed: {e}")
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    rows = []
    if isinstance(raw.columns, pd.MultiIndex):
        available = raw.columns.get_level_values(1).unique()
        for ticker in tickers:
            t = ticker.upper()
            if t not in available:
                continue
            try:
                df = raw.xs(t, axis=1, level=1).dropna(how="all").reset_index()
                df["Ticker"] = t
                rows.append(df)
            except Exception:
                continue
    else:
        # Single-ticker fallback
        df = raw.dropna(how="all").reset_index()
        df["Ticker"] = tickers[0].upper() if tickers else "UNKNOWN"
        rows.append(df)

    if not rows:
        return pd.DataFrame()

    result = pd.concat(rows, ignore_index=True)
    result["Date"] = pd.to_datetime(result["Date"]).dt.tz_localize(None).dt.normalize()
    return result


def _trim(df: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    """Keep the most recent max_rows rows per ticker."""
    return (
        df.sort_values("Date")
        .groupby("Ticker", group_keys=False)
        .tail(max_rows)
        .reset_index(drop=True)
    )


def _filter_by_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Return only rows within the requested period window."""
    days = PERIOD_TO_DAYS.get(period)
    if days is None:
        return df
    cutoff = pd.Timestamp.now(tz=None).normalize() - pd.Timedelta(days=days)
    date_col = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    return df[date_col >= cutoff].reset_index(drop=True)


def _split_by_ticker(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Split long-format DataFrame into {ticker: per-ticker DataFrame}."""
    result = {}
    for ticker, grp in df.groupby("Ticker"):
        result[str(ticker)] = grp.drop(columns=["Ticker"]).reset_index(drop=True)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


def download_ohlcv_cached(
    tickers: List[str],
    period: str = "1y",
    cache_dir: str = DEFAULT_CACHE_DIR,
    **kwargs,
) -> Dict[str, pd.DataFrame]:
    """Download OHLCV data with incremental disk caching.

    Behaviour:
    - **First call** for a ticker universe: downloads the full `period` of
      history and saves it to ``{cache_dir}/{key}.parquet``.
    - **Same-day call**: served from disk — no network traffic.
    - **Next-day call**: fetches only the new trading days (delta), appends
      them to the cached parquet, deduplicates, and saves.

    The `period` parameter controls the *initial* download size and the window
    returned to the caller.  If the cache already contains more history (e.g.
    a 1y cache serves a 6mo caller by slicing), no extra download occurs.

    Args:
        tickers:   List of ticker symbols (case-insensitive).
        period:    yfinance period string ("1y", "6mo", "3mo", …).
        cache_dir: Directory for parquet + meta files.
        **kwargs:  Extra kwargs forwarded to ``yf.download`` (e.g. ``interval``).

    Returns:
        Dict mapping ticker → DataFrame with columns
        [Date, Open, High, Low, Close, Volume].
    """
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    tickers_upper = [t.upper() for t in tickers]
    key = _cache_key(tickers_upper)
    parquet_path, meta_path = _paths(cache_dir, key)
    today = datetime.now().strftime("%Y-%m-%d")
    meta = _read_meta(meta_path)

    # ── Case 1: Fresh cache (updated today) ───────────────────────────────
    if parquet_path.exists() and meta and meta.get("last_updated") == today:
        logger.info(f"OHLCV cache hit ({len(tickers_upper)} tickers, updated today)")
        df = pd.read_parquet(parquet_path)
        return _split_by_ticker(_filter_by_period(df, period))

    # ── Case 2: Stale cache — incremental update ──────────────────────────
    if parquet_path.exists() and meta and meta.get("last_updated"):
        last_updated = meta["last_updated"]
        start_dt = datetime.strptime(last_updated, "%Y-%m-%d") + timedelta(days=1)
        start_str = start_dt.strftime("%Y-%m-%d")

        logger.info(
            f"OHLCV cache stale (last: {last_updated}) — "
            f"fetching {start_str} → today for {len(tickers_upper)} tickers..."
        )

        new_data = _batch_download(tickers_upper, start=start_str, **kwargs)
        existing = pd.read_parquet(parquet_path)

        if not new_data.empty:
            combined = pd.concat([existing, new_data], ignore_index=True)
            # Dedup on (Date, Ticker) — keep latest version of each row
            combined = combined.drop_duplicates(subset=["Date", "Ticker"], keep="last")
            combined = _trim(combined, MAX_ROWS_PER_TICKER)
            combined.to_parquet(parquet_path, index=False)
            logger.info(
                f"Incremental update: {len(new_data)} new rows appended "
                f"({len(existing)} → {len(combined)} total rows)"
            )
        else:
            logger.info("No new rows in incremental fetch — cache unchanged")
            combined = existing

        _write_meta(meta_path, {"last_updated": today, "tickers": tickers_upper, "period": period})
        return _split_by_ticker(_filter_by_period(combined, period))

    # ── Case 3: No cache — full download ──────────────────────────────────
    logger.info(f"OHLCV cache miss — downloading {len(tickers_upper)} tickers ({period})...")
    df = _batch_download(tickers_upper, period=period, **kwargs)

    if df.empty:
        logger.warning("Full download returned empty data — cache not written")
        return {}

    df = _trim(df, MAX_ROWS_PER_TICKER)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parquet_path, index=False)
    _write_meta(meta_path, {"last_updated": today, "tickers": tickers_upper, "period": period})
    logger.info(f"Cache written: {len(df)} rows for {df['Ticker'].nunique()} tickers")
    return _split_by_ticker(_filter_by_period(df, period))
