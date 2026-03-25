"""Unified report-path helpers.

Every CLI command and internal save routine should use these helpers so that
all generated artifacts land under a single ``reports/`` tree.

When a ``run_id`` is supplied the layout becomes::

    reports/
    └── daily/{YYYY-MM-DD}/
        ├── runs/{run_id}/
        │   ├── market/                # scan results
        │   ├── {TICKER}/              # per-ticker analysis
        │   └── portfolio/             # PM artefacts
        ├── latest.json                # pointer → most recent run_id
        └── daily_digest.md            # append-only (shared across runs)

Without a ``run_id`` the legacy flat layout is preserved for backward
compatibility::

    reports/
    └── daily/{YYYY-MM-DD}/
        ├── market/
        ├── {TICKER}/
        └── summary.md
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Configurable via TRADINGAGENTS_REPORTS_DIR env var.
# Falls back to "reports" (relative to CWD) when unset.
REPORTS_ROOT = Path(os.getenv("TRADINGAGENTS_REPORTS_DIR") or "reports")


# ──────────────────────────────────────────────────────────────────────────────
# Run-ID helpers
# ──────────────────────────────────────────────────────────────────────────────

def generate_run_id() -> str:
    """Return a short, human-readable run identifier (8-char hex)."""
    return uuid.uuid4().hex[:8]


def write_latest_pointer(date: str, run_id: str, base_dir: Path | None = None) -> Path:
    """Write ``{base}/daily/{date}/latest.json`` pointing to *run_id*.

    Args:
        date:     ISO date string.
        run_id:   Short identifier for the run.
        base_dir: Reports root directory.  Falls back to ``REPORTS_ROOT``
                  when ``None``.

    Returns the path of the written file.
    """
    root = base_dir or REPORTS_ROOT
    daily = root / "daily" / date
    daily.mkdir(parents=True, exist_ok=True)
    pointer = daily / "latest.json"
    payload = {
        "run_id": run_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    pointer.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return pointer


def read_latest_pointer(date: str, base_dir: Path | None = None) -> str | None:
    """Read the latest run_id for *date*, or ``None`` if no pointer exists.

    Args:
        date:     ISO date string.
        base_dir: Reports root directory.  Falls back to ``REPORTS_ROOT``
                  when ``None``.
    """
    root = base_dir or REPORTS_ROOT
    pointer = root / "daily" / date / "latest.json"
    if not pointer.exists():
        return None
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
        return data.get("run_id")
    except (json.JSONDecodeError, OSError):
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Path helpers
# ──────────────────────────────────────────────────────────────────────────────

def _run_prefix(date: str, run_id: str | None) -> Path:
    """Base directory for a date, optionally scoped by run_id."""
    daily = REPORTS_ROOT / "daily" / date
    if run_id:
        return daily / "runs" / run_id
    return daily


def get_daily_dir(date: str, run_id: str | None = None) -> Path:
    """``reports/daily/{date}/`` or ``reports/daily/{date}/runs/{run_id}/``"""
    return _run_prefix(date, run_id)


def get_market_dir(date: str, run_id: str | None = None) -> Path:
    """``…/{date}[/runs/{run_id}]/market/``"""
    return get_daily_dir(date, run_id) / "market"


def get_ticker_dir(date: str, ticker: str, run_id: str | None = None) -> Path:
    """``…/{date}[/runs/{run_id}]/{TICKER}/``"""
    return get_daily_dir(date, run_id) / ticker.upper()


def get_eval_dir(date: str, ticker: str, run_id: str | None = None) -> Path:
    """``…/{date}[/runs/{run_id}]/{TICKER}/eval/``"""
    return get_ticker_dir(date, ticker, run_id) / "eval"


def get_digest_path(date: str) -> Path:
    """``reports/daily/{date}/daily_digest.md``

    The digest is always at the date level (shared across runs).
    """
    return REPORTS_ROOT / "daily" / date / "daily_digest.md"
