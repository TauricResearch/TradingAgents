"""Helpers for downloading ticker data as ZIP, CSV, or JSON archives."""

from __future__ import annotations

import csv
import io
import logging
import os
import zipfile
from pathlib import Path
from typing import Any

from . import storage

log = logging.getLogger(__name__)


def generate_summary_csv(ticker: str) -> str:
    """Return a CSV string summarizing all runs for a ticker."""
    fieldnames = [
        "run_id",
        "ticker",
        "started_at",
        "finished_at",
        "status",
        "decision_action",
        "decision_target",
        "decision_confidence",
        "llm_provider",
        "deep_think_model",
        "start_price",
        "total_duration_s",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for r in storage.list_ticker_runs(ticker.upper(), limit=5000):
        writer.writerow(
            {
                "run_id": r.get("id", ""),
                "ticker": r.get("ticker", ""),
                "started_at": r.get("started_at") or "",
                "finished_at": r.get("finished_at") or "",
                "status": r.get("status", ""),
                "decision_action": r.get("decision_action") or "",
                "decision_target": r.get("decision_target") if r.get("decision_target") is not None else "",
                "decision_confidence": r.get("decision_confidence") if r.get("decision_confidence") is not None else "",
                "llm_provider": r.get("llm_provider") or "",
                "deep_think_model": r.get("deep_think_model") or "",
                "start_price": r.get("start_price") if r.get("start_price") is not None else "",
                "total_duration_s": r.get("total_duration_s") if r.get("total_duration_s") is not None else "",
            }
        )

    return output.getvalue()


def generate_full_csv(ticker: str) -> str:
    """Return a CSV string with all run data including events for each run."""
    fieldnames = [
        "run_id",
        "ticker",
        "started_at",
        "finished_at",
        "status",
        "decision_action",
        "decision_target",
        "decision_confidence",
        "llm_provider",
        "deep_think_model",
        "start_price",
        "total_duration_s",
        "events_count",
        "llm_calls_count",
        "completed_stages",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for r in storage.list_ticker_runs(ticker.upper(), limit=5000):
        run_id = r.get("id", "")
        events = storage.list_run_events(run_id) if run_id else []
        llm_calls = storage.list_run_llm_calls(run_id) if run_id else []
        completed_stages = r.get("completed_stages") or []

        writer.writerow(
            {
                "run_id": run_id,
                "ticker": r.get("ticker", ""),
                "started_at": r.get("started_at") or "",
                "finished_at": r.get("finished_at") or "",
                "status": r.get("status", ""),
                "decision_action": r.get("decision_action") or "",
                "decision_target": r.get("decision_target") if r.get("decision_target") is not None else "",
                "decision_confidence": r.get("decision_confidence") if r.get("decision_confidence") is not None else "",
                "llm_provider": r.get("llm_provider") or "",
                "deep_think_model": r.get("deep_think_model") or "",
                "start_price": r.get("start_price") if r.get("start_price") is not None else "",
                "total_duration_s": r.get("total_duration_s") if r.get("total_duration_s") is not None else "",
                "events_count": len(events),
                "llm_calls_count": len(llm_calls),
                "completed_stages": ",".join(completed_stages) if completed_stages else "",
            }
        )

    return output.getvalue()


def generate_ticker_json(ticker: str) -> dict[str, Any]:
    """Return a JSON dict with all runs and their full data for a ticker."""
    safe = storage.safe_ticker_component(ticker).upper()
    runs_data: list[dict[str, Any]] = []

    for r in storage.list_ticker_runs(ticker.upper(), limit=5000):
        run_id = r.get("id", "")
        run_dir = storage.read_run_dir(run_id)
        events = storage.list_run_events(run_id) if run_id else []
        llm_calls = storage.list_run_llm_calls(run_id) if run_id else []

        stages_data: dict[str, Any] = {}
        if run_dir:
            stages_dir = run_dir / "stages"
            if stages_dir.exists():
                for stage_file in stages_dir.iterdir():
                    if stage_file.is_file() and stage_file.suffix == ".json":
                        stage_data = storage.read_json(stage_file)
                        if stage_data:
                            stages_data[stage_file.stem] = stage_data

        run_data: dict[str, Any] = {
            **r,
            "events": events,
            "llm_calls": llm_calls,
            "stages": stages_data,
        }
        runs_data.append(run_data)

    return {
        "ticker": safe,
        "total_runs": len(runs_data),
        "runs": runs_data,
    }


def generate_ticker_zip(ticker: str) -> io.BytesIO:
    """Create a ZIP archive of all data for a ticker, including a summary.csv."""
    safe = storage.safe_ticker_component(ticker).upper()
    ticker_path = storage.data_dir() / safe
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add summary.csv at the root of the ZIP
        summary = generate_summary_csv(ticker)
        zf.writestr("summary.csv", summary)

        # Walk the ticker directory and add all files
        if ticker_path.exists():
            try:
                for root, _dirs, files in os.walk(ticker_path):
                    for filename in files:
                        file_path = Path(root) / filename
                        arc_name = str(file_path.relative_to(ticker_path))
                        zf.write(file_path, arc_name)
            except PermissionError as exc:
                log.warning("download: skipping unreadable path %s: %s", exc.filename or ticker_path, exc)

    buf.seek(0)
    return buf
