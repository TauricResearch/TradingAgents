"""Unified report-path helpers.

Every CLI command and internal save routine should use these helpers so that
all generated artifacts land under a single ``reports/`` tree::

    reports/
    └── daily/{YYYY-MM-DD}/
        ├── market/                    # scan results
        │   ├── geopolitical_report.md
        │   └── ...
        ├── {TICKER}/                  # per-ticker analysis / pipeline
        │   ├── 1_analysts/
        │   ├── ...
        │   ├── complete_report.md
        │   └── eval/
        │       └── full_states_log.json
        └── summary.md                # pipeline combined summary
"""

from __future__ import annotations

from pathlib import Path

REPORTS_ROOT = Path("reports")


def get_daily_dir(date: str) -> Path:
    """``reports/daily/{date}/``"""
    return REPORTS_ROOT / "daily" / date


def get_market_dir(date: str) -> Path:
    """``reports/daily/{date}/market/``"""
    return get_daily_dir(date) / "market"


def get_ticker_dir(date: str, ticker: str) -> Path:
    """``reports/daily/{date}/{TICKER}/``"""
    return get_daily_dir(date) / ticker.upper()


def get_eval_dir(date: str, ticker: str) -> Path:
    """``reports/daily/{date}/{TICKER}/eval/``"""
    return get_ticker_dir(date, ticker) / "eval"


def get_digest_path(date: str) -> Path:
    """``reports/daily/{date}/daily_digest.md``"""
    return get_daily_dir(date) / "daily_digest.md"
