"""Debug logs page — full pipeline log viewer with filtering.

See also: PLAN-desktop.md, F7.
"""

from __future__ import annotations

import json

from nicegui import ui

from desktop.state.runner import PipelineRunner
from tradingagents.progress import ProgressSnapshot

_TYPE_COLORS: dict[str, str] = {
    "System": "blue-4",
    "Agent": "green-4",
    "User": "yellow-4",
    "Data": "purple-4",
    "Tool": "orange-4",
    "Control": "grey-5",
    "Error": "red-4",
}

_MAX_VISIBLE = 200  # Cap visible entries to prevent DOM overload


def render_logs_page(*, runner: PipelineRunner) -> None:
    """Render the logs page content."""
    page = _LogsPage(runner=runner)
    page.build()


class _LogsPage:
    def __init__(self, *, runner: PipelineRunner) -> None:
        self._runner = runner
        self._log_area: ui.column | None = None
        self._filter_type: str = "All"
        self._last_count = 0
        self._timer: ui.timer | None = None

    def build(self) -> None:
        with ui.column().classes("w-full q-pa-md gap-md"):
            ui.label("Debug Logs").classes("text-h5 text-white")
            ui.label(
                "Full pipeline log for troubleshooting. Copy and share with your AI assistant."
            ).classes("text-body2 text-grey-5")

            # Controls
            with ui.row().classes("items-center gap-md"):
                ui.select(
                    label="Filter by type",
                    options=["All", "System", "Agent", "Tool", "Data", "Error"],
                    value="All",
                    on_change=lambda e: self._set_filter(e.value),
                ).props("outlined dense").classes("w-40")

                ui.button(
                    "Copy All",
                    icon="content_copy",
                    on_click=self._copy_logs,
                ).props("flat dense")

            # Log area
            with ui.card().classes("w-full"):
                self._log_area = ui.column().classes(
                    "log-panel w-full gap-none"
                ).style("max-height: 600px; overflow-y: auto")

            # Polling timer — auto-deactivates when runner stops
            self._timer = ui.timer(0.5, self._poll)
            self._poll()  # Initial render

    def _set_filter(self, filter_type: str) -> None:
        self._filter_type = filter_type
        self._last_count = -1  # Force refresh
        self._poll()

    def _poll(self) -> None:
        snap = self._runner.tracker.snapshot()
        total = len(snap.messages) + len(snap.tool_calls)
        if total == self._last_count:
            # Deactivate timer when runner is no longer active
            if not self._runner.is_running and self._timer:
                self._timer.deactivate()
            return
        self._last_count = total
        self._render_logs(snap)

    def _render_logs(self, snap: ProgressSnapshot) -> None:
        if self._log_area is None:
            return

        self._log_area.clear()

        # Merge all entries
        entries: list[tuple[str, str, str]] = []
        for ts, msg_type, content in snap.messages:
            entries.append((ts, msg_type, str(content)))
        for ts, tool_name, args in snap.tool_calls:
            args_str = str(args)
            if len(args_str) > 100:
                args_str = args_str[:97] + "..."
            entries.append((ts, "Tool", f"{tool_name}: {args_str}"))

        # Sort chronologically
        entries.sort(key=lambda x: x[0])

        # Filter
        if self._filter_type != "All":
            entries = [e for e in entries if e[1] == self._filter_type]

        # Cap visible entries to prevent DOM overload
        if len(entries) > _MAX_VISIBLE:
            entries = entries[-_MAX_VISIBLE:]

        with self._log_area:
            if not entries:
                ui.label("No log entries yet.").classes("text-grey-5 q-pa-md")
                return

            for ts, entry_type, content in entries:
                color = _TYPE_COLORS.get(entry_type, "grey")
                with ui.row().classes("items-baseline gap-xs q-py-none"):
                    ui.label(ts).classes("text-caption text-grey-6")
                    ui.label(f"[{entry_type}]").classes(f"text-caption text-{color}")
                    ui.label(content).classes("text-caption text-white").style(
                        "word-break: break-all"
                    )

    async def _copy_logs(self) -> None:
        """Copy all log entries to clipboard."""
        snap = self._runner.tracker.snapshot()
        lines: list[str] = []
        for ts, msg_type, content in snap.messages:
            lines.append(f"{ts} [{msg_type}] {content}")
        for ts, tool_name, args in snap.tool_calls:
            lines.append(f"{ts} [Tool] {tool_name}: {args}")
        lines.sort()

        text = "\n".join(lines)
        # CR-01: use json.dumps for safe JS string escaping
        escaped = json.dumps(text)
        await ui.run_javascript(
            f"navigator.clipboard.writeText({escaped})", respond=False
        )
        ui.notify("Logs copied to clipboard!", type="positive")
