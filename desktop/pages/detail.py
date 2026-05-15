"""Detail page — view a completed analysis and its report sections.

Reads markdown files from the analysis ``result_dir`` and renders them
in expandable sections identical to the live progress view.

See also: PLAN-desktop.md, F3 extension.
"""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from desktop.state.database import HistoryDB

# markdown2 extras — shared with report_section.py for consistency
_MD_EXTRAS: list[str] = [
    "tables",
    "fenced-code-blocks",
    "strike",
    "task_list",
    "cuddled-lists",
    "header-ids",
]


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

                _status_badge(analysis.status)

                ui.button("Back", icon="arrow_back",
                          on_click=lambda: ui.navigate.to("/history")).props(
                    "flat dense"
                )

            # Timing info
            with ui.row().classes("gap-md text-caption text-grey-5"):
                ui.label(f"Started: {analysis.started_at}")
                if analysis.completed_at:
                    ui.label(f"Completed: {analysis.completed_at}")

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
                # Still show logs even without report files
                self._build_logs_section()
                return

            # CR-01: Validate result_dir is under the expected base to
            # prevent path traversal via stored/imported paths.
            root = Path(result_dir).resolve()
            expected_base = (Path.home() / ".tradingagents" / "results").resolve()
            if not str(root).startswith(str(expected_base)):
                ui.label("Invalid result directory.").classes(
                    "text-body2 text-red q-pa-md"
                )
                self._build_logs_section()
                return

            sections = _discover_report_files(root)

            if not sections:
                ui.label("No report files found on disk.").classes(
                    "text-body2 text-grey-5 q-pa-md"
                )
                self._build_logs_section()
                return

            ui.label("Reports").classes("text-h6 text-white q-mt-md")

            # Complete report link if present
            # WR-03: wrap file reads with error handling
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
                        extras=_MD_EXTRAS,
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
                    ui.markdown(content, extras=_MD_EXTRAS).classes(
                        "report-content text-white q-pa-sm"
                    )

            # ── Persisted logs ─────────────────────────────────────
            self._build_logs_section()

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
                    color = _TYPE_COLORS.get(entry.entry_type, "grey")
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
                # CR-01: use json.dumps for safe JS string escaping
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


# ── Report file discovery ──────────────────────────────────────────────

# New format: numbered subdirectories with short names
_PHASE_TITLES: dict[str, str] = {
    "1_analysts": "Analysts",
    "2_research": "Research Team",
    "3_trading": "Trading Team",
    "4_risk": "Risk Management",
    "5_portfolio": "Portfolio Management",
}

_FILE_TITLES: dict[str, str] = {
    # New format (short names in subdirs)
    "fundamentals": "Fundamentals Analysis",
    "market": "Market Analysis",
    "news": "News Analysis",
    "sentiment": "Social Sentiment",
    "bull": "Bull Researcher",
    "bear": "Bear Researcher",
    "manager": "Research Manager Decision",
    "trader": "Trading Team Plan",
    "aggressive": "Aggressive Risk Analyst",
    "neutral": "Neutral Risk Analyst",
    "conservative": "Conservative Risk Analyst",
    "decision": "Portfolio Management Decision",
    # Old format (flat reports/ directory)
    "market_report": "Market Analysis",
    "sentiment_report": "Social Sentiment",
    "news_report": "News Analysis",
    "fundamentals_report": "Fundamentals Analysis",
    "investment_plan": "Research Team Decision",
    "trader_investment_plan": "Trading Team Plan",
    "final_trade_decision": "Portfolio Management Decision",
}


def _discover_report_files(root: Path) -> list[tuple[str, Path]]:
    """Find all report markdown files in either directory layout.

    Returns a list of ``(display_title, path)`` tuples in a logical
    order (analysts → research → trading → risk → portfolio).
    """
    sections: list[tuple[str, Path]] = []

    # New format: numbered subdirectories (1_analysts/, 2_research/, ...)
    phase_dirs = sorted(
        (d for d in root.iterdir() if d.is_dir() and d.name[0].isdigit()),
        key=lambda d: d.name,
    )
    if phase_dirs:
        for phase_dir in phase_dirs:
            phase_label = _PHASE_TITLES.get(phase_dir.name, phase_dir.name)
            for md in sorted(phase_dir.glob("*.md")):
                stem = md.stem
                title = _FILE_TITLES.get(stem, f"{phase_label} — {stem.replace('_', ' ').title()}")
                sections.append((f"{phase_label} / {title}", md))
        return sections

    # Old format: flat reports/ subdirectory
    reports_dir = root / "reports"
    if reports_dir.is_dir():
        for md in sorted(reports_dir.glob("*.md")):
            title = _FILE_TITLES.get(md.stem, md.stem.replace("_", " ").title())
            sections.append((title, md))
        return sections

    # Fallback: any .md files directly in root (excluding complete_report)
    for md in sorted(root.glob("*.md")):
        if md.name == "complete_report.md":
            continue
        title = _FILE_TITLES.get(md.stem, md.stem.replace("_", " ").title())
        sections.append((title, md))

    return sections


_TYPE_COLORS: dict[str, str] = {
    "System": "blue-4",
    "Agent": "green-4",
    "User": "yellow-4",
    "Data": "purple-4",
    "Tool": "orange-4",
    "Control": "grey-5",
    "Error": "red-4",
}


def _status_badge(status: str) -> None:
    """Render a colored status badge."""
    colors = {
        "completed": "green",
        "running": "blue",
        "failed": "red",
        "interrupted": "orange",
    }
    color = colors.get(status, "grey")
    ui.label(status.capitalize()).classes(
        f"text-caption text-white bg-{color} q-px-sm q-py-xs rounded-borders"
    )
