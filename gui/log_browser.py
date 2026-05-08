"""Helpers for reading the existing on-disk log files.

Each run writes ``~/.tradingagents/logs/<TICKER>/TradingAgentsStrategy_logs/full_states_log_<DATE>.json``.
We treat those JSON files as the source of truth for report content and
just discover them lazily — the SQLite ``runs`` table only contains rows
the GUI launched, but the History page should also show CLI runs from
before the GUI existed.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from tradingagents.default_config import DEFAULT_CONFIG


def results_dir() -> Path:
    return Path(str(DEFAULT_CONFIG["results_dir"]))


@st.cache_data(ttl=30, show_spinner=False)
def discover_logs() -> List[Dict[str, Any]]:
    """Walk the results directory and return one entry per state-log file.

    Cached for 30 seconds — long enough that clicking around the History
    page doesn't re-walk the filesystem every interaction, short enough
    that a freshly completed run shows up promptly.

    Two kinds of files are surfaced:
    - **Archived per-run files** under ``<ticker>/TradingAgentsStrategy_logs/runs/``
      named ``<run_id>__<trade_date>__<UTC_ts>.json``. Each run has a
      unique file so re-running the same ticker+date never destroys
      previous transcripts.
    - **Canonical files** at ``full_states_log_<DATE>.json`` for backward
      compatibility (CLI runs from before archival was added). When an
      archive exists for the same (ticker, date), we still surface the
      canonical entry — but the archive rows take precedence and the
      canonical row is annotated as "(legacy)" so duplicates are obvious.
    """
    base = results_dir()
    if not base.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for ticker_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        log_dir = ticker_dir / "TradingAgentsStrategy_logs"
        if not log_dir.exists():
            continue

        # Archived per-run files
        runs_dir = log_dir / "runs"
        archive_keys: set[tuple[str, str]] = set()
        if runs_dir.exists():
            for log_file in sorted(runs_dir.glob("*.json"), reverse=True):
                # Filename is "<run_id>__<date>__<ts>.json"
                parts = log_file.stem.split("__")
                run_id = parts[0] if len(parts) >= 1 else ""
                trade_date = parts[1] if len(parts) >= 2 else "unknown"
                run_ts = parts[2] if len(parts) >= 3 else ""
                try:
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime).isoformat(timespec="seconds")
                except OSError:
                    mtime = ""
                entries.append({
                    "ticker": ticker_dir.name,
                    "trade_date": trade_date,
                    "log_path": str(log_file),
                    "modified_at": mtime,
                    "run_id": run_id,
                    "run_ts": run_ts,
                    "kind": "archive",
                })
                archive_keys.add((ticker_dir.name, trade_date))

        # Canonical files (legacy / CLI-only runs)
        for log_file in sorted(log_dir.glob("full_states_log_*.json"), reverse=True):
            stem = log_file.stem
            trade_date = stem.replace("full_states_log_", "", 1)
            try:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime).isoformat(timespec="seconds")
            except OSError:
                mtime = ""
            entries.append({
                "ticker": ticker_dir.name,
                "trade_date": trade_date,
                "log_path": str(log_file),
                "modified_at": mtime,
                "run_id": "",
                "run_ts": "",
                # Flag entries that are duplicated by an archive — UI hides them by default.
                "kind": "canonical_legacy" if (ticker_dir.name, trade_date) in archive_keys else "canonical",
            })
    entries.sort(key=lambda e: e["modified_at"], reverse=True)
    return entries


def load_log(path: str | Path) -> Optional[Dict[str, Any]]:
    """Load a state log and unwrap GUI archive envelopes.

    Three on-disk shapes coexist:
    - **Canonical** (CLI / pre-archive): the raw graph state dict at the
      top level. Returned as-is.
    - **Old GUI archive** (v0): a copy of the canonical file. Returned as-is.
    - **New GUI archive** (schema_version 1): ``{kind, metadata, state,
      tool_trace}``. We return the inner ``state`` for back-compat with
      callers that read ``state.get('market_report')`` etc. — extra
      metadata is available via :func:`load_archive_full`.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and data.get("kind") == "tradingagents-gui-archive":
        return data.get("state") or {}
    return data


def load_archive_full(path: str | Path) -> Optional[Dict[str, Any]]:
    """Load a state log without unwrapping. Returns the full envelope when
    the file is a GUI archive; returns ``{"state": ..., "metadata": {}}``
    for legacy / canonical files so callers can use one shape."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and data.get("kind") == "tradingagents-gui-archive":
        return data
    return {"kind": "legacy", "metadata": {}, "state": data, "tool_trace": []}


def memory_log_path() -> Path:
    return Path(str(DEFAULT_CONFIG["memory_log_path"]))


def read_memory_log() -> str:
    p = memory_log_path()
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""
