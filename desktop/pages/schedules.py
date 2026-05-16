"""Schedules page — manage recurring pre-market analysis schedules.

Create, enable/disable, and delete scheduled analysis runs.  Each
schedule has a watchlist (comma-separated tickers), a cron-like time
expression, and a timezone.

The scheduler fires in the background; this page just manages the
DB rows and tells the ``Scheduler`` service to arm/disarm timers.

See also: PLAN-features-v3.md, Feature 4.
"""

from __future__ import annotations

import json
from typing import Any

from nicegui import ui

from desktop.services.scheduler import CronExpr
from desktop.state.database import HistoryDB, ScheduleRow


def render_schedules_page(
    *,
    db: HistoryDB,
    scheduler: Any,  # Scheduler — avoid circular import
) -> None:
    """Render the schedules management page."""
    page = _SchedulesPage(db=db, scheduler=scheduler)
    page.build()


class _SchedulesPage:
    def __init__(self, *, db: HistoryDB, scheduler: Any) -> None:
        self._db = db
        self._scheduler = scheduler

    def build(self) -> None:
        with ui.column().classes("w-full q-pa-md gap-md"):
            # Header
            with ui.row().classes("items-center w-full"):
                ui.icon("schedule").classes("text-blue text-h5")
                ui.label("Scheduled Analysis").classes("text-h5 text-white")
                ui.space()

                # Scheduler status
                if self._scheduler and self._scheduler.is_running:
                    ui.badge("Scheduler Active", color="green").props("outline")
                else:
                    ui.badge("Scheduler Inactive", color="grey").props("outline")

                ui.button(
                    "New Schedule", icon="add",
                    on_click=self._show_create_dialog,
                ).props("color=blue")

            # Help text
            ui.label(
                "Automate your analysis runs. Schedules fire at the configured "
                "time and queue tickers through the analysis pipeline."
            ).classes("text-body2 text-grey-5")

            # Schedules list
            self._schedules_container = ui.column().classes("w-full gap-md")
            self._refresh_list()

    def _refresh_list(self) -> None:
        """Reload schedules from DB and rebuild the list."""
        self._schedules_container.clear()
        schedules = self._db.list_schedules()

        with self._schedules_container:
            if not schedules:
                self._build_empty_state()
                return

            for sched in schedules:
                self._build_schedule_card(sched)

    def _build_empty_state(self) -> None:
        """Render empty state when no schedules exist."""
        with ui.card().classes("w-full bg-dark"):
            with ui.column().classes("items-center q-pa-xl gap-md"):
                ui.icon("schedule").classes("text-grey-6 text-h3")
                ui.label("No Schedules Yet").classes("text-h6 text-grey-4")
                ui.label(
                    "Create a schedule to automatically run analysis at "
                    "specific times. Great for pre-market prep."
                ).classes("text-body2 text-grey-5 text-center")
                ui.button(
                    "Create First Schedule", icon="add",
                    on_click=self._show_create_dialog,
                ).props("color=blue")

    def _build_schedule_card(self, sched: ScheduleRow) -> None:
        """Render a single schedule card with controls."""
        is_enabled = bool(sched.is_enabled)

        # Parse cron for display
        try:
            parsed = CronExpr.parse(sched.cron_expr)
            time_label = parsed.human_label()
        except ValueError:
            time_label = sched.cron_expr

        tickers = [t.strip() for t in sched.watchlist.split(",") if t.strip()]

        with ui.card().classes("w-full bg-dark"):
            with ui.row().classes("items-center w-full q-pa-sm"):
                # Enable/disable toggle
                ui.switch(
                    value=is_enabled,
                    on_change=lambda e, sid=sched.id, cron=sched.cron_expr,
                    tz=sched.timezone: self._toggle_schedule(
                        sid, e.value, cron, tz
                    ),
                ).props("color=green")

                # Schedule info
                with ui.column().classes("gap-none"):
                    ui.label(sched.name).classes(
                        f"text-subtitle1 {'text-white' if is_enabled else 'text-grey-6'}"
                    )
                    with ui.row().classes("items-center gap-sm"):
                        ui.icon("access_time", size="xs").classes("text-blue-4")
                        ui.label(time_label).classes("text-caption text-grey-4")
                        ui.label(f"({sched.timezone})").classes("text-caption text-grey-6")

                ui.space()

                # Tickers
                with ui.row().classes("gap-xs"):
                    for ticker in tickers[:5]:  # show up to 5
                        ui.badge(ticker, color="blue-grey").props("outline")
                    if len(tickers) > 5:
                        ui.badge(f"+{len(tickers) - 5}", color="grey").props("outline")

                ui.space()

                # Last / next run info
                with ui.column().classes("gap-none items-end"):
                    if sched.last_run:
                        ui.label(f"Last: {sched.last_run}").classes(
                            "text-caption text-grey-6"
                        )
                    if sched.next_run and is_enabled:
                        ui.label(f"Next: {sched.next_run}").classes(
                            "text-caption text-green-4"
                        )

                # Actions
                with ui.row().classes("gap-xs"):
                    ui.button(
                        icon="play_arrow",
                        on_click=lambda sid=sched.id: self._run_now(sid),
                    ).props("flat dense round color=green").tooltip("Run Now")
                    ui.button(
                        icon="history",
                        on_click=lambda sid=sched.id, name=sched.name: (
                            self._show_run_history(sid, name)
                        ),
                    ).props("flat dense round color=blue").tooltip("Run History")
                    ui.button(
                        icon="delete",
                        on_click=lambda sid=sched.id, name=sched.name: (
                            self._confirm_delete(sid, name)
                        ),
                    ).props("flat dense round color=red").tooltip("Delete")

    def _toggle_schedule(
        self, schedule_id: int, enabled: bool, cron_expr: str, timezone: str,
    ) -> None:
        """Enable or disable a schedule."""
        self._db.update_schedule_enabled(schedule_id, enabled)
        if self._scheduler:
            if enabled:
                self._scheduler.add_schedule(schedule_id, cron_expr, timezone)
            else:
                self._scheduler.remove_schedule(schedule_id)
        status = "enabled" if enabled else "disabled"
        ui.notify(f"Schedule {status}", type="positive")
        self._refresh_list()

    def _run_now(self, schedule_id: int) -> None:
        """Manually trigger a schedule immediately."""
        schedules = self._db.list_schedules()
        sched = next((s for s in schedules if s.id == schedule_id), None)
        if sched is None:
            ui.notify("Schedule not found", type="negative")
            return

        tickers = [t.strip().upper() for t in sched.watchlist.split(",") if t.strip()]
        if not tickers:
            ui.notify("Watchlist is empty", type="warning")
            return

        if self._scheduler:
            try:
                self._scheduler.run_now(schedule_id, tickers)
                ui.notify(
                    f"Dispatched {len(tickers)} ticker(s): {', '.join(tickers)}",
                    type="positive",
                )
            except Exception as exc:
                ui.notify(f"Failed to dispatch: {exc}", type="negative")
        else:
            ui.notify("Scheduler not available", type="warning")

    def _show_create_dialog(self) -> None:
        """Show the dialog to create a new schedule."""
        with ui.dialog() as dialog, ui.card().classes("w-96 bg-dark"):
            ui.label("New Schedule").classes("text-h6 text-white")
            ui.separator().classes("bg-grey-8")

            name_input = ui.input(
                label="Name",
                placeholder="e.g., Pre-Market Scan",
            ).classes("w-full")

            watchlist_input = ui.input(
                label="Watchlist (comma-separated tickers)",
                placeholder="e.g., AAPL, MSFT, NVDA, TSLA",
            ).classes("w-full")

            with ui.row().classes("w-full gap-md"):
                hour_input = ui.number(
                    label="Hour (0-23)", value=8, min=0, max=23,
                    format="%.0f",
                ).classes("w-20")
                minute_input = ui.number(
                    label="Minute (0-59)", value=30, min=0, max=59,
                    format="%.0f",
                ).classes("w-20")

            days_select = ui.select(
                label="Days",
                options=[
                    "MON-FRI",
                    "Every day",
                    "MON,WED,FRI",
                    "TUE,THU",
                    "SAT,SUN",
                ],
                value="MON-FRI",
            ).classes("w-full")

            tz_select = ui.select(
                label="Timezone",
                options=[
                    "America/New_York",
                    "America/Chicago",
                    "America/Denver",
                    "America/Los_Angeles",
                    "UTC",
                    "Europe/London",
                    "Europe/Moscow",
                    "Asia/Tokyo",
                    "Asia/Shanghai",
                ],
                value="America/New_York",
            ).classes("w-full")

            with ui.row().classes("w-full justify-end gap-sm q-mt-md"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button(
                    "Create", icon="add",
                    on_click=lambda: self._create_schedule(
                        dialog=dialog,
                        name=name_input.value or "",
                        watchlist=watchlist_input.value or "",
                        hour=int(hour_input.value or 8),
                        minute=int(minute_input.value or 0),
                        days=days_select.value or "MON-FRI",
                        timezone=tz_select.value or "America/New_York",
                    ),
                ).props("color=blue")

        dialog.open()

    def _create_schedule(
        self,
        *,
        dialog: Any,
        name: str,
        watchlist: str,
        hour: int,
        minute: int,
        days: str,
        timezone: str,
    ) -> None:
        """Validate and create a new schedule."""
        name = name.strip()
        if not name:
            ui.notify("Please enter a schedule name", type="warning")
            return

        tickers = [t.strip().upper() for t in watchlist.split(",") if t.strip()]
        if not tickers:
            ui.notify("Please enter at least one ticker", type="warning")
            return

        # Build cron expression
        days_token = "*" if days == "Every day" else days
        cron_expr = f"{hour:02d}:{minute:02d} {days_token}"

        # Validate
        try:
            CronExpr.parse(cron_expr)
        except ValueError as exc:
            ui.notify(f"Invalid schedule: {exc}", type="negative")
            return

        # Insert into DB
        try:
            schedule_id = self._db.insert_schedule(
                name=name,
                watchlist=", ".join(tickers),
                cron_expr=cron_expr,
                timezone=timezone,
            )
        except Exception as exc:
            ui.notify(f"Failed to create schedule: {exc}", type="negative")
            return

        # Arm the timer
        if self._scheduler:
            self._scheduler.add_schedule(schedule_id, cron_expr, timezone)

        dialog.close()
        ui.notify(f"Schedule '{name}' created", type="positive")
        self._refresh_list()

    def _confirm_delete(self, schedule_id: int, name: str) -> None:
        """Show confirmation dialog before deleting a schedule."""
        with ui.dialog() as dialog, ui.card().classes("bg-dark"):
            ui.label(f"Delete '{name}'?").classes("text-h6 text-white")
            ui.label(
                "This will permanently remove the schedule and all its run history."
            ).classes("text-body2 text-grey-4")

            with ui.row().classes("w-full justify-end gap-sm q-mt-md"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button(
                    "Delete", icon="delete",
                    on_click=lambda: self._delete_schedule(dialog, schedule_id),
                ).props("color=red")

        dialog.open()

    def _delete_schedule(self, dialog: Any, schedule_id: int) -> None:
        """Delete a schedule from DB and disarm its timer."""
        if self._scheduler:
            self._scheduler.remove_schedule(schedule_id)
        self._db.delete_schedule(schedule_id)
        dialog.close()
        ui.notify("Schedule deleted", type="positive")
        self._refresh_list()

    def _show_run_history(self, schedule_id: int, name: str) -> None:
        """Show recent runs for a schedule in a dialog."""
        runs = self._db.list_schedule_runs(schedule_id, limit=20)

        with ui.dialog() as dialog, ui.card().classes("w-128 bg-dark"):
            ui.label(f"Run History — {name}").classes("text-h6 text-white")
            ui.separator().classes("bg-grey-8")

            if not runs:
                ui.label("No runs yet.").classes("text-body2 text-grey-5 q-pa-md")
            else:
                with ui.column().classes(
                    "w-full gap-sm"
                ).style("max-height: 400px; overflow-y: auto"):
                    for run in runs:
                        _color = {
                            "completed": "green",
                            "running": "blue",
                            "failed": "red",
                            "skipped_conflict": "orange",
                        }.get(run.status, "grey")

                        with ui.row().classes("items-center w-full gap-sm"):
                            ui.badge(
                                run.status, color=_color,
                            ).props("outline")
                            ui.label(run.started_at).classes("text-caption text-grey-4")
                            if run.completed_at:
                                ui.label(f"→ {run.completed_at}").classes(
                                    "text-caption text-grey-6"
                                )

                            # Tickers
                            try:
                                tickers = json.loads(run.tickers_json)
                            except (json.JSONDecodeError, TypeError):
                                tickers = []
                            ui.label(", ".join(tickers)).classes(
                                "text-caption text-white"
                            )

            with ui.row().classes("w-full justify-end q-mt-md"):
                ui.button("Close", on_click=dialog.close).props("flat")

        dialog.open()
