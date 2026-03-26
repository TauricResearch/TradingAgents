"""Unified report-path helpers.

Every CLI command and internal save routine should use these helpers so that
all generated artifacts land under a single ``reports/`` tree.

When a ``flow_id`` is supplied the layout becomes::

    reports/
    └── daily/{YYYY-MM-DD}/
        └── {flow_id}/
            ├── market/report/         # scan results (timestamped files)
            ├── {TICKER}/report/       # per-ticker analysis (timestamped)
            ├── portfolio/report/      # PM artefacts (timestamped)
            ├── run_meta.json          # metadata for the latest run
            └── run_events.jsonl       # events for the latest run

When only a legacy ``run_id`` is supplied the layout becomes::

    reports/
    └── daily/{YYYY-MM-DD}/
        ├── runs/{run_id}/             # legacy run-scoped layout
        │   ├── market/
        │   ├── {TICKER}/
        │   └── portfolio/
        ├── latest.json                # pointer → most recent run_id
        └── daily_digest.md            # append-only (shared across runs)

Without a ``run_id`` or ``flow_id`` the legacy flat layout is preserved for
backward compatibility::

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
# ID / timestamp helpers
# ──────────────────────────────────────────────────────────────────────────────

def generate_flow_id() -> str:
    """Return a short, human-readable flow identifier (8-char hex).

    A *flow* groups all phases of one analysis intent (scan + pipeline +
    portfolio).  Prefer :func:`generate_flow_id` for new code.
    """
    return uuid.uuid4().hex[:8]


def generate_run_id() -> str:
    """Return a short, human-readable run identifier (8-char hex).

    .. deprecated::
        Use :func:`generate_flow_id` for new code.  ``generate_run_id``
        is kept for backward compatibility only.
    """
    return uuid.uuid4().hex[:8]


def ts_now() -> str:
    """Return a sortable UTC timestamp string: ``'20260325T143022123Z'`` (ms precision).

    Used as a filename prefix so that lexicographic sort gives temporal order
    and ``load_*`` helpers can always find the most recent report without a
    separate pointer file.  Millisecond precision prevents same-second collisions.
    """
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%S") + f"{dt.microsecond // 1000:03d}Z"


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

def _run_prefix(date: str, run_id: str | None, flow_id: str | None = None) -> Path:
    """Base directory for a date, scoped by flow_id or legacy run_id.

    Resolution order:
    1. ``flow_id`` → ``daily/{date}/{flow_id}`` (new layout, no ``runs/`` prefix)
    2. ``run_id``  → ``daily/{date}/runs/{run_id}`` (legacy layout)
    3. Neither     → ``daily/{date}`` (flat legacy layout)
    """
    daily = REPORTS_ROOT / "daily" / date
    if flow_id:
        return daily / flow_id
    if run_id:
        return daily / "runs" / run_id
    return daily


def get_daily_dir(
    date: str,
    run_id: str | None = None,
    *,
    flow_id: str | None = None,
) -> Path:
    """``reports/daily/{date}/[{flow_id}/|runs/{run_id}/]``"""
    return _run_prefix(date, run_id, flow_id)


def get_market_dir(
    date: str,
    run_id: str | None = None,
    *,
    flow_id: str | None = None,
) -> Path:
    """``…/{date}[/{flow_id}|/runs/{run_id}]/market/``"""
    return get_daily_dir(date, run_id, flow_id=flow_id) / "market"


def get_ticker_dir(
    date: str,
    ticker: str,
    run_id: str | None = None,
    *,
    flow_id: str | None = None,
) -> Path:
    """``…/{date}[/{flow_id}|/runs/{run_id}]/{TICKER}/``"""
    return get_daily_dir(date, run_id, flow_id=flow_id) / ticker.upper()


def get_eval_dir(
    date: str,
    ticker: str,
    run_id: str | None = None,
    *,
    flow_id: str | None = None,
) -> Path:
    """``…/{date}[/{flow_id}|/runs/{run_id}]/{TICKER}/eval/``"""
    return get_ticker_dir(date, ticker, run_id, flow_id=flow_id) / "eval"


def get_digest_path(date: str) -> Path:
    """``reports/daily/{date}/daily_digest.md``

    The digest is always at the date level (shared across runs).
    """
    return REPORTS_ROOT / "daily" / date / "daily_digest.md"
