"""History page — past analyses table with search and filtering.

Includes a **Resume** button for interrupted/failed analyses that have
LangGraph checkpoints on disk (same ticker+date → auto-resume from
the last successful node).

See also: PLAN-desktop.md, F3.
"""

from __future__ import annotations

import json

from nicegui import ui

from desktop.state.database import HistoryDB
from desktop.state.runner import PipelineRunner


def render_history_page(*, db: HistoryDB, runner: PipelineRunner | None = None) -> None:
    """Render the history page content."""
    page = _HistoryPage(db=db, runner=runner)
    page.build()


class _HistoryPage:
    def __init__(self, *, db: HistoryDB, runner: PipelineRunner | None = None) -> None:
        self._db = db
        self._runner = runner
        self._search = ""
        self._table: ui.table | None = None
        self._selected: list[dict] = []
        self._compare_btn: ui.button | None = None

    def build(self) -> None:
        with ui.column().classes("w-full q-pa-md gap-md"):
            ui.label("Analysis History").classes("text-h5 text-white")

            # Search bar + Compare button
            with ui.row().classes("items-center gap-sm"):
                ui.input(
                    "Search ticker...",
                    on_change=lambda e: self._refresh(e.value),
                ).props("outlined dense clearable").classes("w-64")
                ui.button("Refresh", icon="refresh", on_click=lambda: self._refresh()).props(
                    "flat dense"
                )
                ui.space()
                self._compare_btn = ui.button(
                    "Compare", icon="compare_arrows",
                    on_click=self._on_compare,
                ).props("flat dense color=purple")
                self._compare_btn.set_visibility(False)

            # Table
            columns = [
                {"name": "id", "label": "ID", "field": "id", "sortable": True},
                {"name": "ticker", "label": "Ticker", "field": "ticker", "sortable": True},
                {"name": "date", "label": "Date", "field": "date", "sortable": True},
                {"name": "provider", "label": "Provider", "field": "provider"},
                {"name": "status", "label": "Status", "field": "status", "sortable": True},
                {"name": "started_at", "label": "Started", "field": "started_at", "sortable": True},
                {"name": "completed_at", "label": "Completed", "field": "completed_at"},
                {"name": "actions", "label": "", "field": "actions"},
            ]
            self._table = ui.table(
                columns=columns,
                rows=[],
                row_key="id",
                pagination={"rowsPerPage": 15},
                selection="multiple",
                on_select=lambda e: self._on_selection_change(e.selection),
            ).classes("w-full").props("flat bordered dense")

            # Add "View" + "Resume" buttons via slot
            self._table.add_slot(
                "body-cell-actions",
                """
                <q-td :props="props">
                    <q-btn flat dense color="green" icon="visibility" label="View"
                           @click="$parent.$emit('view', props.row)" />
                    <q-btn v-if="props.row.status === 'interrupted' || props.row.status === 'failed'"
                           flat dense color="orange" icon="replay" label="Resume"
                           @click="$parent.$emit('resume', props.row)" />
                </q-td>
                """,
            )

            def _on_view(e) -> None:
                # CR-02: validate client-controlled ID before navigation
                try:
                    aid = int(e.args["id"])
                except (KeyError, TypeError, ValueError):
                    ui.notify("Invalid analysis ID", type="warning")
                    return
                ui.navigate.to(f"/analysis/{aid}")

            def _on_resume(e) -> None:
                try:
                    aid = int(e.args["id"])
                except (KeyError, TypeError, ValueError):
                    ui.notify("Invalid analysis ID", type="warning")
                    return
                self._resume_analysis(aid)

            self._table.on("view", _on_view)
            self._table.on("resume", _on_resume)

            self._refresh()

    def _on_selection_change(self, selection: list[dict]) -> None:
        """Update compare button visibility based on selection count."""
        self._selected = selection
        count = len(selection)
        if self._compare_btn:
            self._compare_btn.set_visibility(count == 2)
            if count == 2:
                self._compare_btn.set_text(
                    f"Compare #{selection[0]['id']} vs #{selection[1]['id']}"
                )

    def _on_compare(self) -> None:
        """Navigate to the comparison page with the two selected analyses."""
        if len(self._selected) != 2:
            ui.notify("Select exactly 2 analyses to compare", type="warning")
            return
        id_a = self._selected[0]["id"]
        id_b = self._selected[1]["id"]
        ui.navigate.to(f"/compare/{id_a}/{id_b}")

    def _resume_analysis(self, analysis_id: int) -> None:
        """Resume an interrupted/failed analysis using its saved checkpoint.

        Reads ticker, date, config, and selected_analysts from the DB row,
        creates a new DB entry (so each attempt is tracked), and starts the
        pipeline.  LangGraph finds the checkpoint via the deterministic
        thread_id = SHA256(ticker:date) and resumes from the last saved node.
        """
        if self._runner is None:
            ui.notify("Runner not available", type="negative")
            return

        if self._runner.is_running:
            ui.notify("Another analysis is already running", type="warning")
            return

        row = self._db.get_analysis(analysis_id)
        if row is None:
            ui.notify("Analysis not found", type="negative")
            return

        if row.status not in ("interrupted", "failed"):
            ui.notify(f"Cannot resume — status is '{row.status}'", type="warning")
            return

        # Reconstruct config from the saved JSON
        try:
            config: dict = json.loads(row.config_json) if row.config_json else {}
        except json.JSONDecodeError:
            config = {}

        selected_analysts = [
            a.strip() for a in (row.selected_analysts or "").split(",") if a.strip()
        ] or ["market", "social", "news", "fundamentals"]

        # Create a new DB row for this resume attempt
        new_id = self._db.insert_analysis(
            ticker=row.ticker,
            date=row.date,
            provider=row.provider,
            model=row.model,
            config=config,
            selected_analysts=selected_analysts,
        )

        try:
            self._runner.start(
                config=config,
                ticker=row.ticker,
                date=row.date,
                selected_analysts=selected_analysts,
                analysis_id=new_id,
            )
        except RuntimeError as e:
            # CR-02: Clean up orphaned "running" row on start failure
            self._db.mark_interrupted(new_id)
            ui.notify(str(e), type="negative")
            return

        ui.notify(
            f"Resuming {row.ticker} from checkpoint — continuing where it left off",
            type="positive",
            timeout=8000,
        )
        ui.navigate.to("/")

    def _refresh(self, search: str | None = None) -> None:
        if search is not None:
            self._search = search.strip()

        ticker_filter = self._search.upper() if self._search else None
        analyses = self._db.list_analyses(ticker=ticker_filter, limit=100)

        rows = [
            {
                "id": a.id,
                "ticker": a.ticker,
                "date": a.date,
                "provider": a.provider,
                "status": a.status,
                "started_at": a.started_at,
                "completed_at": a.completed_at or "",
            }
            for a in analyses
        ]

        if self._table:
            self._table.rows = rows
            self._table.update()
