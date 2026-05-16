"""Alerts page -- active price alerts and fired alert history.

Displays the alert engine status, unseen notifications, the active
alerts table, and a full history of fired alerts.  Auto-refreshes
every 10 seconds to pick up newly fired alerts.

See also: PLAN-desktop.md, Phase 3 -- Price Alerts.
"""

from __future__ import annotations

import logging

from nicegui import ui

from desktop.services.alert_engine import AlertEngine
from desktop.state.database import AlertHistoryRow, AlertRow, HistoryDB

logger = logging.getLogger(__name__)


def render_alerts_page(*, db: HistoryDB, alert_engine: AlertEngine) -> None:
    """Render the alerts page content."""
    page = _AlertsPage(db=db, alert_engine=alert_engine)
    page.build()


class _AlertsPage:
    """Internal page controller for the alerts view."""

    def __init__(self, *, db: HistoryDB, alert_engine: AlertEngine) -> None:
        self._db = db
        self._engine = alert_engine

        # UI refs for auto-refresh updates
        self._status_icon: ui.icon | None = None
        self._status_label: ui.label | None = None
        self._unseen_container: ui.column | None = None
        self._active_table: ui.table | None = None
        self._history_table: ui.table | None = None
        self._empty_state: ui.column | None = None

    def build(self) -> None:
        """Render the full page layout."""
        with ui.column().classes("w-full q-pa-md gap-md"):
            self._build_header()
            self._build_unseen_section()
            self._build_active_table()
            self._build_history_table()
            self._build_empty_state()

            # Initial data load
            self._refresh()

            # Auto-refresh every 10 seconds
            ui.timer(10.0, self._refresh)

    # ------------------------------------------------------------------
    # Header + engine status
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        """Page title with engine health indicator."""
        with ui.row().classes("items-center w-full"):
            ui.label("Price Alerts").classes("text-h5 text-white")

            ui.space()

            # Engine status indicator
            with ui.row().classes("items-center gap-xs"):
                self._status_icon = ui.icon("circle").classes("text-caption")
                self._status_label = ui.label("").classes(
                    "text-caption text-grey-4"
                )

            self._update_engine_status()

    def _update_engine_status(self) -> None:
        """Refresh the engine status indicator."""
        if self._status_icon is None or self._status_label is None:
            return

        if not self._engine.is_running:
            self._status_icon.classes(replace="text-caption text-grey-6")
            self._status_label.set_text("Engine stopped")
        elif self._engine.is_degraded:
            backoff = self._engine.backoff_seconds
            minutes = backoff // 60
            self._status_icon.classes(replace="text-caption text-yellow-6")
            self._status_label.set_text(
                f"Degraded -- retry in {minutes}m"
            )
        else:
            self._status_icon.classes(replace="text-caption text-green-6")
            last = self._engine.last_poll_at
            suffix = f" -- last poll {last}" if last else ""
            self._status_label.set_text(f"Healthy{suffix}")

    # ------------------------------------------------------------------
    # Unseen alerts section
    # ------------------------------------------------------------------

    def _build_unseen_section(self) -> None:
        """Container for unseen alert notifications."""
        self._unseen_container = ui.column().classes("w-full gap-sm")

    def _populate_unseen(self, unseen: list[AlertHistoryRow]) -> None:
        """Rebuild the unseen alerts cards."""
        if self._unseen_container is None:
            return

        self._unseen_container.clear()

        if not unseen:
            return

        with self._unseen_container:
            with ui.row().classes("items-center w-full"):
                ui.label(
                    f"{len(unseen)} unseen alert(s)"
                ).classes("text-subtitle1 text-yellow-4")
                ui.space()
                ui.button(
                    "Mark all seen",
                    icon="done_all",
                    on_click=lambda: self._mark_all_seen(unseen),
                ).props("flat dense color=yellow")

            for entry in unseen:
                with ui.card().classes(
                    "w-full bg-yellow-10 q-pa-sm"
                ).style("border-left: 4px solid #f9a825"):
                    with ui.row().classes("items-center w-full"):
                        ui.icon("notifications_active").classes(
                            "text-yellow-4"
                        )
                        ui.label(entry.message).classes(
                            "text-body2 text-white q-ml-sm"
                        )
                        ui.space()
                        ui.label(f"${entry.price:.2f}").classes(
                            "text-body2 text-white"
                        )
                        ui.label(entry.fired_at).classes(
                            "text-caption text-grey-5 q-ml-sm"
                        )

    def _mark_all_seen(self, unseen: list[AlertHistoryRow]) -> None:
        """Mark all unseen alerts as seen and refresh."""
        ids = [entry.id for entry in unseen]
        if ids:
            try:
                self._db.mark_alerts_seen(ids)
                ui.notify(
                    f"Marked {len(ids)} alert(s) as seen", type="positive"
                )
            except Exception:
                logger.exception("Failed to mark alerts as seen")
                ui.notify("Failed to mark alerts as seen", type="negative")
                return
        self._refresh()

    # ------------------------------------------------------------------
    # Active alerts table
    # ------------------------------------------------------------------

    def _build_active_table(self) -> None:
        """Table of active (untriggered) alerts."""
        ui.label("Active Alerts").classes("text-h6 text-white q-mt-md")

        columns = [
            {
                "name": "ticker",
                "label": "Ticker",
                "field": "ticker",
                "sortable": True,
            },
            {
                "name": "alert_type",
                "label": "Type",
                "field": "alert_type",
                "sortable": True,
            },
            {
                "name": "target_price",
                "label": "Target Price",
                "field": "target_price",
                "sortable": True,
            },
            {
                "name": "direction",
                "label": "Direction",
                "field": "direction",
                "sortable": True,
            },
            {
                "name": "created_at",
                "label": "Created",
                "field": "created_at",
                "sortable": True,
            },
        ]

        self._active_table = ui.table(
            columns=columns,
            rows=[],
            row_key="id",
            pagination={"rowsPerPage": 15},
        ).classes("w-full").props("flat bordered dense")

    def _populate_active_table(self, alerts: list[AlertRow]) -> None:
        """Refresh active alerts table rows."""
        if self._active_table is None:
            return

        rows = [
            {
                "id": a.id,
                "ticker": a.ticker,
                "alert_type": _format_alert_type(a.alert_type),
                "target_price": f"${a.target_price:.2f}",
                "direction": a.direction.capitalize(),
                "created_at": a.created_at,
            }
            for a in alerts
        ]

        self._active_table.rows = rows
        self._active_table.update()

    # ------------------------------------------------------------------
    # Alert history table
    # ------------------------------------------------------------------

    def _build_history_table(self) -> None:
        """Table of all fired alerts (full history)."""
        ui.label("Alert History").classes("text-h6 text-white q-mt-md")

        columns = [
            {
                "name": "fired_at",
                "label": "Fired At",
                "field": "fired_at",
                "sortable": True,
            },
            {
                "name": "message",
                "label": "Message",
                "field": "message",
            },
            {
                "name": "price",
                "label": "Price",
                "field": "price",
                "sortable": True,
            },
            {
                "name": "seen",
                "label": "Seen",
                "field": "seen",
                "sortable": True,
            },
        ]

        self._history_table = ui.table(
            columns=columns,
            rows=[],
            row_key="id",
            pagination={"rowsPerPage": 15},
        ).classes("w-full").props("flat bordered dense")

    def _populate_history_table(
        self, history: list[AlertHistoryRow]
    ) -> None:
        """Refresh alert history table rows."""
        if self._history_table is None:
            return

        rows = [
            {
                "id": h.id,
                "fired_at": h.fired_at,
                "message": h.message,
                "price": f"${h.price:.2f}",
                "seen": "Yes" if h.seen else "No",
            }
            for h in history
        ]

        self._history_table.rows = rows
        self._history_table.update()

    # ------------------------------------------------------------------
    # Empty state
    # ------------------------------------------------------------------

    def _build_empty_state(self) -> None:
        """Placeholder shown when no alerts exist."""
        self._empty_state = ui.column().classes(
            "w-full items-center q-pa-xl"
        )

    def _update_empty_state(
        self,
        *,
        has_active: bool,
        has_history: bool,
    ) -> None:
        """Show or hide the empty state message."""
        if self._empty_state is None:
            return

        self._empty_state.clear()

        if has_active or has_history:
            self._empty_state.set_visibility(False)
            return

        self._empty_state.set_visibility(True)
        with self._empty_state:
            ui.icon("notifications_none").classes(
                "text-grey-6 text-h2 q-mb-md"
            )
            ui.label("No alerts yet").classes("text-h6 text-grey-5")
            ui.label(
                "Alerts are created automatically when you run analyses "
                "with price levels."
            ).classes("text-body2 text-grey-6 text-center")

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Reload all data from the database and update every section."""
        try:
            unseen = self._db.list_unseen_alert_history()
            active = self._db.list_active_alerts()
            history = self._db.list_all_alert_history()
        except Exception:
            logger.exception("Failed to load alert data")
            return

        self._update_engine_status()
        self._populate_unseen(unseen)
        self._populate_active_table(active)
        self._populate_history_table(history)
        self._update_empty_state(
            has_active=len(active) > 0,
            has_history=len(history) > 0,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_alert_type(alert_type: str) -> str:
    """Human-readable label for an alert type."""
    labels = {
        "stop_loss": "Stop Loss",
        "entry_trigger": "Entry Trigger",
        "profit_target": "Profit Target",
        "custom": "Custom",
    }
    return labels.get(alert_type, alert_type.replace("_", " ").title())
