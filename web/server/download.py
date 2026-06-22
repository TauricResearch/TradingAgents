"""Helpers for downloading ticker data as ZIP archives with summary CSVs."""

from __future__ import annotations

import csv
import io
import os
import zipfile
from pathlib import Path

from . import storage


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

    for r in storage.list_ticker_runs(ticker.upper(), limit=500):
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
            for root, _dirs, files in os.walk(ticker_path):
                for filename in files:
                    file_path = Path(root) / filename
                    arc_name = str(file_path.relative_to(ticker_path))
                    zf.write(file_path, arc_name)

    buf.seek(0)
    return buf
