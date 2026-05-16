"""Compare page — side-by-side view of two analyses.

Renders two analyses in parallel columns with price charts, report
sections, and a summary diff strip at the top.

Entry point: ``/compare?a={id1}&b={id2}`` from the History page.

See also: PLAN-features-v2.md, Feature 2.
"""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from desktop.components.price_chart import PriceChart
from desktop.state.database import AnalysisRow, HistoryDB
from desktop.utils.paths import validated_result_dir
from desktop.utils.reports import (
    MD_EXTRAS,
    discover_report_files,
    status_chip,
)


def render_compare_page(*, db: HistoryDB, id_a: int, id_b: int) -> None:
    """Render the comparison page for two analyses."""
    page = _ComparePage(db=db, id_a=id_a, id_b=id_b)
    page.build()


class _ComparePage:
    def __init__(self, *, db: HistoryDB, id_a: int, id_b: int) -> None:
        self._db = db
        self._id_a = id_a
        self._id_b = id_b

    def build(self) -> None:
        a = self._db.get_analysis(self._id_a)
        b = self._db.get_analysis(self._id_b)

        if a is None or b is None:
            with ui.column().classes("w-full q-pa-md"):
                missing = []
                if a is None:
                    missing.append(str(self._id_a))
                if b is None:
                    missing.append(str(self._id_b))
                ui.label(
                    f"Analysis not found: {', '.join(missing)}"
                ).classes("text-h5 text-red")
                ui.button(
                    "Back to History", icon="arrow_back",
                    on_click=lambda: ui.navigate.to("/history"),
                )
            return

        with ui.column().classes("w-full q-pa-md gap-md"):
            # Back button + title
            with ui.row().classes("items-center gap-md"):
                ui.button(
                    icon="arrow_back",
                    on_click=lambda: ui.navigate.to("/history"),
                ).props("flat dense")
                ui.label("Compare Analyses").classes("text-h5 text-white")

            # Diff summary strip
            self._build_diff_strip(a, b)

            # Two-column layout
            with ui.grid(columns=2).classes("w-full gap-md"):
                # Column A
                with ui.column().classes("gap-md"):
                    self._build_analysis_column(a, label="A")

                # Column B
                with ui.column().classes("gap-md"):
                    self._build_analysis_column(b, label="B")

    def _build_diff_strip(self, a: AnalysisRow, b: AnalysisRow) -> None:
        """Summary card highlighting key differences."""
        with ui.card().classes("w-full"):
            with ui.row().classes("items-center gap-lg"):
                ui.icon("compare_arrows").classes("text-purple text-h5")
                ui.label("Comparison Summary").classes("text-subtitle1")

            with ui.grid(columns=3).classes("w-full q-mt-sm"):
                # Column headers
                ui.label("").classes("text-caption text-grey")
                ui.label(f"Analysis A (#{a.id})").classes(
                    "text-caption text-blue-4 text-bold"
                )
                ui.label(f"Analysis B (#{b.id})").classes(
                    "text-caption text-orange-4 text-bold"
                )

                # Ticker
                ui.label("Ticker").classes("text-caption text-grey")
                _diff_cell(a.ticker, b.ticker, a.ticker)
                _diff_cell(b.ticker, a.ticker, b.ticker)

                # Date
                ui.label("Date").classes("text-caption text-grey")
                _diff_cell(a.date, b.date, a.date)
                _diff_cell(b.date, a.date, b.date)

                # Provider
                ui.label("Provider").classes("text-caption text-grey")
                ui.label(a.provider).classes("text-caption")
                ui.label(b.provider).classes("text-caption")

                # Status
                ui.label("Status").classes("text-caption text-grey")
                status_chip(a.status)
                status_chip(b.status)

            # Decision comparison (if both have result files)
            decision_a = _read_decision(a)
            decision_b = _read_decision(b)
            if decision_a or decision_b:
                ui.separator().classes("q-my-sm")
                with ui.row().classes("gap-lg"):
                    with ui.column().classes("w-1/2"):
                        ui.label("Decision A").classes(
                            "text-caption text-blue-4"
                        )
                        ui.label(decision_a or "N/A").classes(
                            "text-body2 text-white"
                        )
                    with ui.column().classes("w-1/2"):
                        ui.label("Decision B").classes(
                            "text-caption text-orange-4"
                        )
                        ui.label(decision_b or "N/A").classes(
                            "text-body2 text-white"
                        )

    def _build_analysis_column(
        self, analysis: AnalysisRow, *, label: str,
    ) -> None:
        """Render one analysis column with header, chart, and reports."""
        color = "blue" if label == "A" else "orange"

        # Header strip
        with ui.card().classes(f"w-full border-{color}"):
            with ui.row().classes("items-center"):
                ui.label(label).classes(
                    f"text-h6 text-{color} text-bold q-mr-sm"
                )
                ui.label(analysis.ticker).classes("text-h6 text-white")
                ui.label(analysis.date).classes("text-caption text-grey q-ml-sm")
                status_chip(analysis.status)

        # Price chart
        PriceChart(
            ticker=analysis.ticker, analysis_date=analysis.date,
        ).build()

        # Report sections from disk
        if not analysis.result_dir or not Path(analysis.result_dir).is_dir():
            ui.label("No report files on disk.").classes(
                "text-body2 text-grey-5"
            )
            return

        # SEC-01: Use is_relative_to instead of fragile startswith
        root = validated_result_dir(analysis.result_dir)
        if root is None:
            ui.label("Invalid result directory.").classes("text-body2 text-red")
            return

        sections = discover_report_files(root)

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


# ── Helpers ───────────────────────────────────────────────────────────────


def _read_decision(analysis: AnalysisRow) -> str | None:
    """Try to extract the first line of the final trade decision.

    BUG-02 fix: validates result_dir before reading files.
    """
    if not analysis.result_dir:
        return None

    # BUG-02: Validate path before reading (was missing here)
    root = validated_result_dir(analysis.result_dir)
    if root is None:
        return None

    candidates = [
        root / "5_portfolio" / "decision.md",
        root / "final_trade_decision.md",
        root / "reports" / "final_trade_decision.md",
    ]
    for path in candidates:
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8").strip()
                # Return first non-empty, non-header line
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        return stripped[:200]
            except (OSError, UnicodeDecodeError):
                pass
    return None


def _diff_cell(value: str, other: str, display: str) -> None:
    """Render a cell that highlights when values differ."""
    if value != other:
        ui.label(display).classes("text-caption text-yellow text-bold")
    else:
        ui.label(display).classes("text-caption")
