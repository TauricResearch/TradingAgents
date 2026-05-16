"""Scrolling message log panel.

Displays recent messages and tool calls from the ProgressTracker
with auto-scroll and a capped visible window.
"""

from __future__ import annotations

from nicegui import ui

from desktop.utils.reports import TYPE_COLORS
from tradingagents.progress import ProgressSnapshot

_MAX_VISIBLE = 20


class LogPanel:
    """Scrollable log panel showing recent messages.

    Call ``update(snapshot)`` from the UI timer.
    """

    def __init__(self) -> None:
        self._container: ui.column | None = None
        self._last_count = 0

    def build(self) -> None:
        """Render the log panel layout."""
        with ui.card().classes("w-full"):
            with ui.row().classes("items-center"):
                ui.icon("terminal").classes("text-grey-5")
                ui.label("Live Log").classes("text-subtitle2")
            self._container = ui.column().classes("log-panel w-full q-mt-xs gap-none")

    def update(self, snap: ProgressSnapshot) -> None:
        """Refresh the log from a snapshot."""
        total = len(snap.messages) + len(snap.tool_calls)
        if total == self._last_count:
            return  # No new messages
        self._last_count = total

        if self._container is None:
            return

        self._container.clear()
        with self._container:
            # Merge messages and tool calls, sort by timestamp
            all_entries: list[tuple[str, str, str]] = []

            for ts, msg_type, content in snap.messages:
                all_entries.append((ts, msg_type, _truncate(str(content), 120)))

            for ts, tool_name, args in snap.tool_calls:
                args_str = str(args)
                if len(args_str) > 60:
                    args_str = args_str[:57] + "..."
                all_entries.append((ts, "Tool", f"{tool_name}: {args_str}"))

            # Sort newest first, take last N
            all_entries.sort(key=lambda x: x[0], reverse=True)
            visible = all_entries[:_MAX_VISIBLE]

            for ts, entry_type, content in visible:
                color = TYPE_COLORS.get(entry_type, "grey")
                with ui.row().classes("items-baseline gap-xs q-py-none"):
                    ui.label(ts).classes("text-caption text-grey-6")
                    ui.label(f"[{entry_type}]").classes(f"text-caption text-{color}")
                    ui.label(content).classes("text-caption text-white")


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
