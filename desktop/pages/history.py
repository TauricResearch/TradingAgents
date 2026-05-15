"""History page — past analyses table with search and filtering.

See also: PLAN-desktop.md, F3.
"""

from __future__ import annotations

from nicegui import ui

from desktop.state.database import HistoryDB


def render_history_page(*, db: HistoryDB) -> None:
    """Render the history page content."""
    page = _HistoryPage(db=db)
    page.build()


class _HistoryPage:
    def __init__(self, *, db: HistoryDB) -> None:
        self._db = db
        self._search = ""
        self._table: ui.table | None = None

    def build(self) -> None:
        with ui.column().classes("w-full q-pa-md gap-md"):
            ui.label("Analysis History").classes("text-h5 text-white")

            # Search bar
            with ui.row().classes("items-center gap-sm"):
                ui.input(
                    "Search ticker...",
                    on_change=lambda e: self._refresh(e.value),
                ).props("outlined dense clearable").classes("w-64")
                ui.button("Refresh", icon="refresh", on_click=lambda: self._refresh()).props(
                    "flat dense"
                )

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
            ).classes("w-full").props("flat bordered dense")

            # Add "View" button column via slot
            self._table.add_slot(
                "body-cell-actions",
                """
                <q-td :props="props">
                    <q-btn flat dense color="green" icon="visibility" label="View"
                           @click="$parent.$emit('view', props.row)" />
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

            self._table.on("view", _on_view)

            self._refresh()

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
