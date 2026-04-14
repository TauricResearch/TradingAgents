#!/usr/bin/env python3
"""Nightly OHLCV prefetch — populates the shared cache for all scanners.

Run nightly at 01:00 UTC (before discovery at 12:30 UTC) so scanners read
from disk instead of hitting yfinance at run time.

First run: downloads 1y of history for the full ticker universe (~592 tickers).
Subsequent runs: appends only the new trading day's bars (incremental update).

Usage:
    python scripts/prefetch_ohlcv.py
    python scripts/prefetch_ohlcv.py --period 6mo   # shorter initial window
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tradingagents.dataflows.data_cache.ohlcv_cache import download_ohlcv_cached
from tradingagents.dataflows.universe import load_universe
from tradingagents.default_config import DEFAULT_CONFIG


def main():
    parser = argparse.ArgumentParser(description="Prefetch OHLCV data for the ticker universe")
    parser.add_argument(
        "--period",
        default="1y",
        help="History window for initial download (default: 1y). Incremental runs ignore this.",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(ROOT / "data" / "ohlcv_cache"),
        help="Directory to store parquet cache files",
    )
    args = parser.parse_args()

    tickers = load_universe(DEFAULT_CONFIG)
    if not tickers:
        print("ERROR: No tickers loaded — check data/tickers.txt", flush=True)
        sys.exit(1)

    print(f"Prefetching OHLCV for {len(tickers)} tickers (period={args.period})...", flush=True)
    print(f"Cache dir: {args.cache_dir}", flush=True)

    start = time.time()
    data = download_ohlcv_cached(
        tickers=tickers,
        period=args.period,
        cache_dir=args.cache_dir,
    )
    elapsed = time.time() - start

    # Summary
    n_tickers = len(data)
    total_rows = sum(len(df) for df in data.values())
    cache_size_mb = (
        sum(p.stat().st_size for p in Path(args.cache_dir).glob("*.parquet")) / 1024 / 1024
    )

    print(f"\nDone in {elapsed:.1f}s", flush=True)
    print(f"  Tickers cached : {n_tickers}/{len(tickers)}", flush=True)
    print(f"  Total rows     : {total_rows:,}", flush=True)
    print(f"  Cache size     : {cache_size_mb:.1f} MB", flush=True)

    missing = set(tickers) - set(data.keys())
    if missing:
        print(f"  Missing tickers: {len(missing)} (delisted or no data)", flush=True)


if __name__ == "__main__":
    main()
