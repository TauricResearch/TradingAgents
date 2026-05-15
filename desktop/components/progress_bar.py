"""Progress indicator for the analysis pipeline.

Shows completed reports / total reports with elapsed time and
a heartbeat indicator (last activity).
"""

from __future__ import annotations

import time

from nicegui import ui

from tradingagents.progress import ProgressSnapshot


class ProgressPanel:
    """Reactive progress bar + stats strip.

    Call ``update(snapshot)`` from the UI timer.
    """

    def __init__(self) -> None:
        self._progress: ui.linear_progress | None = None
        self._label: ui.label | None = None
        self._elapsed: ui.label | None = None
        self._heartbeat: ui.label | None = None
        self._start_time: float | None = None

    def build(self) -> None:
        """Render the progress bar layout."""
        with ui.card().classes("w-full ta-progress"):
            with ui.row().classes("items-center w-full"):
                ui.icon("assessment").classes("text-green text-h6")
                ui.label("Analysis Progress").classes("text-subtitle1")
                ui.space()
                self._elapsed = ui.label("00:00").classes("text-caption text-grey")

            self._progress = ui.linear_progress(value=0, show_value=False).classes(
                "q-mt-sm"
            ).props("color=green size=8px rounded")

            with ui.row().classes("items-center q-mt-xs"):
                self._label = ui.label("0 / 0 reports").classes("text-caption")
                ui.space()
                self._heartbeat = ui.label("").classes("text-caption text-grey")

    def start(self) -> None:
        """Mark the start time for elapsed display."""
        self._start_time = time.time()

    def update(self, snap: ProgressSnapshot, *, total_reports: int) -> None:
        """Refresh from a progress snapshot."""
        # Report progress
        completed = sum(
            1 for section, content in snap.report_sections.items()
            if content is not None
        )
        fraction = completed / max(total_reports, 1)

        if self._progress:
            self._progress.set_value(fraction)
        if self._label:
            self._label.set_text(f"{completed} / {total_reports} reports")

        # Elapsed time
        if self._elapsed and self._start_time:
            elapsed = time.time() - self._start_time
            mins, secs = divmod(int(elapsed), 60)
            self._elapsed.set_text(f"{mins:02d}:{secs:02d}")

        # Heartbeat
        if self._heartbeat and snap.last_activity:
            from datetime import datetime
            delta = datetime.now() - snap.last_activity
            secs_ago = int(delta.total_seconds())
            if secs_ago < 5:
                self._heartbeat.set_text("Active now")
                self._heartbeat.classes(replace="text-caption text-green")
            elif secs_ago < 60:
                self._heartbeat.set_text(f"Last activity {secs_ago}s ago")
                self._heartbeat.classes(replace="text-caption text-grey")
            else:
                mins_ago = secs_ago // 60
                self._heartbeat.set_text(f"No activity for {mins_ago}m")
                self._heartbeat.classes(replace="text-caption text-red")
