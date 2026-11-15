"""Run-ID isolated, staged report/manifest publication with one commit point."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from tradingagents.dataflows.symbols import safe_ticker_component


@dataclass(frozen=True)
class PublishedArtifacts:
    run_dir: Path
    report_path: Path
    manifest_path: Path
    terminal_event_durable: bool


class PersistenceError(OSError):
    pass


def publish_run(results_dir: str | Path, ticker: str, run_id: str,
                report_markdown: str, report_html: str | None,
                manifest: dict, event_sink, redactor, *, state_data: dict | None = None,
                message_log: str | None = None, terminal_outcome: str = "COMPLETED") -> PublishedArtifacts:
    root = Path(results_dir)
    safe_ticker = safe_ticker_component(ticker)
    staging_root = root / "_staging"
    final_dir = root / safe_ticker / run_id
    staging_dir = staging_root / run_id
    try:
        staging_root.mkdir(parents=True, exist_ok=True)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        if final_dir.exists() or staging_dir.exists():
            raise FileExistsError("Run identifier already exists; refusing to overwrite artifacts.")
        staging_dir.mkdir()
        reports = staging_dir / "reports"
        reports.mkdir()
        (reports / "complete_report.md").write_text(redactor.scrub(report_markdown), encoding="utf-8")
        if report_html is not None:
            (reports / "complete_report.html").write_text(redactor.scrub(report_html), encoding="utf-8")

        # These legacy-compatible sinks are deliberately best-effort and run-ID isolated.
        for filename, content in (("state.json", state_data), ("message_tool.log", message_log)):
            if content is None:
                continue
            try:
                destination = staging_dir / filename
                if filename.endswith(".json"):
                    destination.write_text(json.dumps(redactor.scrub(content), ensure_ascii=False,
                                                       sort_keys=True, indent=2) + "\n", encoding="utf-8")
                else:
                    destination.write_text(redactor.scrub(content), encoding="utf-8")
            except OSError:
                event_sink.emit("output", "output.persist", f"BEST_EFFORT_FAILED:{filename}")
        event_sink.emit("output", "output.persist", "STAGED")
        event_sink.emit("output", "run.terminal", terminal_outcome)
        terminal_durable = event_sink.write_to(staging_dir / "events.jsonl")
        safe_manifest = redactor.scrub({
            **manifest,
            "report_paths": {
                "markdown": "reports/complete_report.md",
                "html": "reports/complete_report.html" if report_html is not None else None,
            },
            "terminal_event": {"logical": "run.terminal", "durable": terminal_durable},
        })
        temporary_manifest = staging_dir / "manifest.json.tmp"
        temporary_manifest.write_text(
            json.dumps(safe_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_manifest, staging_dir / "manifest.json")
        # Same-filesystem directory rename is the only publication action.
        if final_dir.exists():
            raise FileExistsError("Run directory appeared during publication; refusing overwrite.")
        os.rename(staging_dir, final_dir)
        return PublishedArtifacts(final_dir, final_dir / "reports" / "complete_report.md",
                                  final_dir / "manifest.json", terminal_durable)
    except Exception as exc:
        try:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
        except OSError:
            pass
        if isinstance(exc, PersistenceError):
            raise
        raise PersistenceError("Could not publish the run artifacts.") from exc
