"""Run history: scan the shared results tree, manifests, report loading.

One shared history: web runs write the identical ``{TICKER}/{date}/reports/``
tree the CLI writes, plus a ``run.json`` manifest carrying metadata that is
recoverable from nowhere else on disk (decision, models, duration). CLI-era
runs (no manifest) degrade gracefully: listed from directory names, decision
unknown, source "cli". No sqlite index — a two-level directory scan with an
in-process cache keyed on directory mtimes is plenty at localhost scale.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from tradingagents.web.projection import REPORT_SECTIONS

logger = logging.getLogger(__name__)

MANIFEST_NAME = "run.json"

# Section file names written incrementally into reports/ by both CLI and web
# (cli/main.py REPORT_SECTIONS keys), in display order.
REPORT_SECTION_KEYS = tuple(REPORT_SECTIONS)

_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def write_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def read_manifest(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Unreadable run manifest: %s", path)
        return None
    return data if isinstance(data, dict) else None


def load_report(results_dir: str | Path, ticker: str, date: str) -> dict[str, Any] | None:
    """Return the per-section markdown for a run, or None if no run exists.

    Falls back to ``complete_report.md`` when no section files are present
    (some CLI-era runs only saved the consolidated report).
    """
    run_dir = Path(results_dir) / ticker / date
    reports_dir = run_dir / "reports"
    if not run_dir.is_dir():
        return None

    sections: dict[str, str] = {}
    for key in REPORT_SECTION_KEYS:
        path = reports_dir / f"{key}.md"
        if path.is_file():
            try:
                sections[key] = path.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Unreadable report section: %s", path)

    complete = None
    if not sections:
        complete_path = reports_dir / "complete_report.md"
        if complete_path.is_file():
            try:
                complete = complete_path.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Unreadable report: %s", complete_path)

    if not sections and complete is None:
        return None
    return {
        "ticker": ticker,
        "date": date,
        "sections": sections,
        "complete_report": complete,
        "manifest": read_manifest(run_dir),
    }


class RunHistory:
    """Directory scanner with an mtime-keyed per-run entry cache."""

    def __init__(self, results_dir: str | Path):
        self.results_dir = Path(results_dir)
        self._cache: dict[tuple[str, str], tuple[float, dict]] = {}

    def list_runs(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        root = self.results_dir
        if not root.is_dir():
            return entries

        for ticker_dir in root.iterdir():
            if not ticker_dir.is_dir():
                continue
            for date_dir in ticker_dir.iterdir():
                if not date_dir.is_dir() or not _DATE_DIR.match(date_dir.name):
                    continue
                key = (ticker_dir.name, date_dir.name)
                seen.add(key)
                try:
                    mtime = date_dir.stat().st_mtime
                except OSError:
                    continue
                cached = self._cache.get(key)
                if cached is not None and cached[0] == mtime:
                    entries.append(cached[1])
                    continue
                entry = self._build_entry(ticker_dir.name, date_dir.name, date_dir)
                self._cache[key] = (mtime, entry)
                entries.append(entry)

        for stale in set(self._cache) - seen:
            del self._cache[stale]

        entries.sort(key=lambda e: (e["date"], e["ticker"]), reverse=True)
        return entries

    def _build_entry(self, ticker: str, date: str, run_dir: Path) -> dict[str, Any]:
        manifest = read_manifest(run_dir)
        has_report = (run_dir / "reports").is_dir()
        if manifest is None:
            return {
                "ticker": ticker,
                "date": date,
                "source": "cli",
                "status": "done" if has_report else "unknown",
                "decision": None,
                "has_report": has_report,
            }
        entry = {
            "ticker": manifest.get("ticker", ticker),
            "date": manifest.get("date", date),
            "source": "web",
            "run_id": manifest.get("run_id"),
            "status": manifest.get("status"),
            "decision": manifest.get("decision"),
            "asset_type": manifest.get("asset_type"),
            "provider": manifest.get("provider"),
            "deep_think_llm": manifest.get("deep_think_llm"),
            "quick_think_llm": manifest.get("quick_think_llm"),
            "analysts": manifest.get("analysts"),
            "started_at": manifest.get("started_at"),
            "finished_at": manifest.get("finished_at"),
            "duration_seconds": manifest.get("duration_seconds"),
            "error": manifest.get("error"),
            "has_report": has_report,
        }
        return entry
