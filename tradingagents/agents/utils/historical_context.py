"""Lookup helpers for prior-run reports (read-only, filesystem-backed).

These are intentionally tiny and pure: they walk the
``reports/daily/{date}/{run_id}/...`` tree looking for the most recent
artifact that predates ``as_of_date`` and falls within ``lookback_days``.

The functions never raise on missing files — they return ``None`` so callers
can fall back gracefully.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.report_paths import REPORTS_ROOT


def _parse_iso(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _candidate_dates(
    reports_root: Path,
    as_of_date: str,
    lookback_days: int,
) -> list[str]:
    target = _parse_iso(as_of_date)
    if target is None or not reports_root.exists():
        return []
    earliest = target - timedelta(days=lookback_days)
    out: list[date] = []
    for child in reports_root.iterdir():
        if not child.is_dir():
            continue
        d = _parse_iso(child.name)
        if d is None:
            continue
        if earliest <= d < target:
            out.append(d)
    out.sort(reverse=True)
    return [d.isoformat() for d in out]


def _load_latest_in_date(
    date_dir: Path,
    relative_subpath: str,
    filename_tail: str,
) -> dict[str, Any] | None:
    """Return the JSON data from the lexicographically-last file whose name ends with
    ``filename_tail``, scanning all run-id subdirectories under ``date_dir / relative_subpath``.

    Returns ``None`` on any error or if no matching file exists.
    """
    if not date_dir.exists():
        return None
    matches: list[Path] = []
    for run_dir in date_dir.iterdir():
        if not run_dir.is_dir():
            continue
        scan_dir = run_dir / relative_subpath
        if not scan_dir.exists():
            continue
        matches.extend(p for p in scan_dir.iterdir() if p.is_file() and p.name.endswith(filename_tail))
    if not matches:
        return None
    matches.sort(key=lambda p: (p.parent.parent.name, p.name), reverse=True)
    try:
        return json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def find_latest_prior_analysis(
    ticker: str,
    as_of_date: str,
    reports_root: Path | None = None,
    lookback_days: int | None = None,
) -> dict[str, Any] | None:
    """Return the most recent ``complete_report.json`` strictly before ``as_of_date``.

    Returns ``{"date": "YYYY-MM-DD", "data": {...}}`` or ``None``.
    """
    root = Path(reports_root) if reports_root is not None else Path(REPORTS_ROOT) / "daily"
    lookback = (
        lookback_days
        if lookback_days is not None
        else int(DEFAULT_CONFIG.get("historical_context_lookback_days", 60))
    )
    for d in _candidate_dates(root, as_of_date, lookback):
        data = _load_latest_in_date(
            root / d,
            f"{ticker.upper()}/report",
            "complete_report.json",
        )
        if data is not None:
            return {"date": d, "data": data}
    return None


def find_latest_prior_pm_decision(
    portfolio_id: str,
    as_of_date: str,
    reports_root: Path | None = None,
    lookback_days: int | None = None,
) -> dict[str, Any] | None:
    """Return the most recent ``{portfolio_id}_pm_decision.json`` strictly before ``as_of_date``."""
    root = Path(reports_root) if reports_root is not None else Path(REPORTS_ROOT) / "daily"
    lookback = (
        lookback_days
        if lookback_days is not None
        else int(DEFAULT_CONFIG.get("historical_context_lookback_days", 60))
    )
    for d in _candidate_dates(root, as_of_date, lookback):
        data = _load_latest_in_date(
            root / d,
            "portfolio/report",
            f"{portfolio_id}_pm_decision.json",
        )
        if data is not None:
            return {"date": d, "data": data}
    return None
