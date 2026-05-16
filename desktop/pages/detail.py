"""Detail page — view a completed analysis and its report sections.

Reads markdown files from the analysis ``result_dir`` and renders them
in expandable sections identical to the live progress view.

See also: PLAN-desktop.md, F3 extension.
"""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from desktop.components.price_chart import PriceChart
from desktop.state.database import HistoryDB
from desktop.utils.paths import validated_result_dir
from desktop.utils.reports import (
    MD_EXTRAS,
    TYPE_COLORS,
    discover_report_files,
    status_chip,
)


def render_detail_page(*, db: HistoryDB, analysis_id: int) -> None:
    """Render the detail page for a single completed analysis."""
    page = _DetailPage(db=db, analysis_id=analysis_id)
    page.build()


class _DetailPage:
    def __init__(self, *, db: HistoryDB, analysis_id: int) -> None:
        self._db = db
        self._analysis_id = analysis_id

    def build(self) -> None:
        analysis = self._db.get_analysis(self._analysis_id)
        if analysis is None:
            with ui.column().classes("w-full q-pa-md"):
                ui.label("Analysis not found").classes("text-h5 text-red")
                ui.button("Back to History", icon="arrow_back",
                          on_click=lambda: ui.navigate.to("/history"))
            return

        with ui.column().classes("w-full q-pa-md gap-md"):
            # Header strip
            with ui.row().classes("items-center w-full bg-dark q-pa-sm rounded-borders"):
                ui.icon("analytics").classes("text-green text-h5")
                ui.label(analysis.ticker).classes("text-h6 text-white q-ml-sm")
                ui.label(analysis.date).classes("text-caption text-grey q-ml-sm")
                ui.label(analysis.provider).classes("text-caption text-grey q-ml-sm")
                ui.label(analysis.model).classes("text-caption text-grey q-ml-sm")

                ui.space()

                status_chip(analysis.status)

                # PDF export button
                if analysis.result_dir and Path(analysis.result_dir).is_dir():
                    _aid = analysis  # capture for closure
                    ui.button(
                        "Export PDF", icon="picture_as_pdf",
                        on_click=lambda a=_aid: self._export_pdf(a),
                    ).props("flat dense color=blue")

                ui.button("Back", icon="arrow_back",
                          on_click=lambda: ui.navigate.to("/history")).props(
                    "flat dense"
                )

            # Timing info
            with ui.row().classes("gap-md text-caption text-grey-5"):
                ui.label(f"Started: {analysis.started_at}")
                if analysis.completed_at:
                    ui.label(f"Completed: {analysis.completed_at}")

            # Price chart
            PriceChart(
                ticker=analysis.ticker, analysis_date=analysis.date,
            ).build()

            # Error text (if failed)
            if analysis.error_text:
                ui.label(f"Error: {analysis.error_text}").classes(
                    "text-body2 text-red q-pa-sm bg-dark rounded-borders"
                )

            # Report sections
            result_dir = analysis.result_dir
            if not result_dir or not Path(result_dir).is_dir():
                ui.label("No report files found on disk.").classes(
                    "text-body2 text-grey-5 q-pa-md"
                )
                self._build_logs_section()
                return

            # SEC-01: Use is_relative_to instead of fragile startswith
            root = validated_result_dir(result_dir)
            if root is None:
                ui.label("Invalid result directory.").classes(
                    "text-body2 text-red q-pa-md"
                )
                self._build_logs_section()
                return

            sections = discover_report_files(root)

            if not sections:
                ui.label("No report files found on disk.").classes(
                    "text-body2 text-grey-5 q-pa-md"
                )
                self._build_logs_section()
                return

            ui.label("Reports").classes("text-h6 text-white q-mt-md")

            # Complete report link if present
            complete = root / "complete_report.md"
            if complete.exists():
                try:
                    complete_text = complete.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as exc:
                    complete_text = f"*Error reading report: {exc}*"
                with ui.expansion(
                    "Complete Report", icon="summarize",
                ).classes("w-full bg-dark").props(
                    "dense header-class='text-subtitle1 text-green-4'"
                ):
                    ui.markdown(
                        complete_text,
                        extras=MD_EXTRAS,
                    ).classes("report-content text-white q-pa-sm")

            # Individual sections
            for title, md_path in sections:
                try:
                    content = md_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as exc:
                    content = f"*Error reading report: {exc}*"
                with ui.expansion(
                    title, icon="description",
                ).classes("w-full bg-dark").props(
                    "dense header-class='text-subtitle2 text-grey-4'"
                ):
                    ui.markdown(content, extras=MD_EXTRAS).classes(
                        "report-content text-white q-pa-sm"
                    )

            # Persisted logs
            self._build_logs_section()

    def _export_pdf(self, analysis: object) -> None:
        """Export this analysis as PDF."""
        try:
            from desktop.services.pdf_export import PDFExporter

            exporter = PDFExporter()
            pdf_path = exporter.export_analysis(
                result_dir=Path(analysis.result_dir),
                ticker=analysis.ticker,
                verdict="",  # will be read from the report
                date=analysis.date,
            )
            ui.notify(f"PDF exported: {pdf_path.name}", type="positive")
            # Open the file
            import subprocess
            subprocess.Popen(["open", str(pdf_path)])
        except ImportError:
            ui.notify(
                "weasyprint not installed. Run: pip install weasyprint",
                type="warning",
                close_button=True,
            )
        except Exception as exc:
            ui.notify(f"Export failed: {exc}", type="negative")

    def _build_logs_section(self) -> None:
        """Render persisted log entries from the database."""
        log_count = self._db.count_log_entries(self._analysis_id)
        if log_count == 0:
            return

        ui.label(f"Logs ({log_count})").classes("text-h6 text-white q-mt-lg")

        # Filter selector
        filter_type = {"value": "All"}

        def refresh_logs(entry_type: str = "All") -> None:
            filter_type["value"] = entry_type
            et = entry_type if entry_type != "All" else None
            entries = self._db.get_log_entries(self._analysis_id, entry_type=et)
            log_area.clear()
            with log_area:
                if not entries:
                    ui.label("No entries match this filter.").classes(
                        "text-grey-5 q-pa-md"
                    )
                    return
                for entry in entries:
                    color = TYPE_COLORS.get(entry.entry_type, "grey")
                    with ui.row().classes("items-baseline gap-xs q-py-none"):
                        ui.label(entry.timestamp).classes("text-caption text-grey-6")
                        ui.label(f"[{entry.entry_type}]").classes(
                            f"text-caption text-{color}"
                        )
                        ui.label(entry.content).classes(
                            "text-caption text-white"
                        ).style("word-break: break-all")

        with ui.row().classes("items-center gap-md"):
            ui.select(
                label="Filter by type",
                options=["All", "System", "Agent", "Tool", "Data", "Error"],
                value="All",
                on_change=lambda e: refresh_logs(e.value),
            ).props("outlined dense").classes("w-40")

            async def copy_all() -> None:
                import json as _json

                entries = self._db.get_log_entries(self._analysis_id)
                text = "\n".join(
                    f"{e.timestamp} [{e.entry_type}] {e.content}" for e in entries
                )
                # SECURITY: json.dumps is required here to prevent JS injection
                escaped = _json.dumps(text)
                await ui.run_javascript(
                    f"navigator.clipboard.writeText({escaped})", respond=False
                )
                ui.notify("Logs copied!", type="positive")

            ui.button("Copy All", icon="content_copy", on_click=copy_all).props(
                "flat dense"
            )

        with ui.card().classes("w-full"):
            log_area = ui.column().classes(
                "w-full gap-none"
            ).style("max-height: 500px; overflow-y: auto")

        refresh_logs()
