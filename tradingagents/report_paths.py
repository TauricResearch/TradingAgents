"""Unified report-path helpers.

Every generated artifact lands under a single process-scoped directory:

    reports/
    └── daily/{YYYY-MM-DD}/
        └── {run_id}/
            ├── market/report/
            ├── {TICKER}/report/
            ├── portfolio/report/
            ├── run_meta.json
            └── run_events.jsonl

The canonical identifier is always ``run_id``. There is no separate flow id.
"""

from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

# Configurable via TRADINGAGENTS_REPORTS_DIR env var.
REPORTS_ROOT = Path(os.getenv("TRADINGAGENTS_REPORTS_DIR") or "reports")

_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_crockford(value: int, length: int) -> str:
    chars = ["0"] * length
    for idx in range(length - 1, -1, -1):
        chars[idx] = _CROCKFORD32[value & 0x1F]
        value >>= 5
    return "".join(chars)


def generate_run_id() -> str:
    """Return a 26-character ULID string."""
    timestamp_ms = int(time.time() * 1000)
    randomness = secrets.randbits(80)
    return _encode_crockford(timestamp_ms, 10) + _encode_crockford(randomness, 16)


def ts_now() -> str:
    """Return a sortable UTC timestamp string with millisecond precision."""
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%S") + f"{dt.microsecond // 1000:03d}Z"


def get_daily_dir(date: str, run_id: str | None = None) -> Path:
    """Return ``reports/daily/{date}`` or ``reports/daily/{date}/{run_id}``."""
    daily = REPORTS_ROOT / "daily" / date
    if run_id:
        return daily / run_id
    return daily


def get_market_dir(date: str, run_id: str | None = None) -> Path:
    """Return ``…/{date}/{run_id}/market`` when run_id is set."""
    return get_daily_dir(date, run_id) / "market"


def get_ticker_dir(date: str, ticker: str, run_id: str | None = None) -> Path:
    """Return ``…/{date}/{run_id}/{TICKER}`` when run_id is set."""
    return get_daily_dir(date, run_id) / ticker.upper()


def get_eval_dir(date: str, ticker: str, run_id: str | None = None) -> Path:
    """Return ``…/{date}/{run_id}/{TICKER}/eval`` when run_id is set."""
    return get_ticker_dir(date, ticker, run_id) / "eval"


def get_digest_path(date: str) -> Path:
    """Return the shared daily digest path."""
    return REPORTS_ROOT / "daily" / date / "daily_digest.md"
