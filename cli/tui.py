"""Textual-based live view for `tradingagents analyze`.

Mirrors the panes of the classic Rich Live renderer (header / progress /
messages / report / footer) but routes them through Textual widgets so the
report and message panes are scrollable. Selected via the absence of
`--classic`; the classic path remains in `cli.main.run_analysis` for one
release.

The graph stream loop is blocking, so it runs in a Textual worker thread
(`@work(thread=True)`). Buffer mutations are funnelled back to the UI via
`app.call_from_thread(...)` and a fixed-cadence refresh interval, matching
the `refresh_per_second=4` of the classic renderer.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from rich import box
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Markdown, Static

# --- Rich renderable builders -------------------------------------------------
# Pure functions of buffer state. No Textual coupling, easy to unit-test, and
# reusable from the classic renderer if we ever consolidate.

_STATUS_COLORS = {"pending": "yellow", "completed": "green", "error": "red"}


def _status_cell(status: str):
    if status == "in_progress":
        return Spinner("dots", text="[blue]in_progress[/blue]", style="bold cyan")
    color = _STATUS_COLORS.get(status, "white")
    return f"[{color}]{status}[/{color}]"


def build_progress_table(buffer) -> Table:
    from cli.main import ALL_TEAMS  # canonical mapping; defined in cli.main

    table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        box=box.SIMPLE_HEAD,
        padding=(0, 2),
        expand=True,
    )
    table.add_column("Team", style="cyan", justify="center", width=20)
    table.add_column("Agent", style="green", justify="center", width=20)
    table.add_column("Status", style="yellow", justify="center", width=20)

    teams = {}
    for team, agents in ALL_TEAMS.items():
        active = [a for a in agents if a in buffer.agent_status]
        if active:
            teams[team] = active

    for team, agents in teams.items():
        first = agents[0]
        table.add_row(
            team, first, _status_cell(buffer.agent_status.get(first, "pending"))
        )
        for agent in agents[1:]:
            table.add_row(
                "", agent, _status_cell(buffer.agent_status.get(agent, "pending"))
            )
        table.add_row("─" * 20, "─" * 20, "─" * 20, style="dim")
    return table


def build_messages_table(buffer, limit: int | None = None) -> Table:
    """Build the messages & tools table.

    `limit=None` shows everything (TUI mode — outer VerticalScroll handles
    overflow). The classic renderer passes `limit=12`.
    """
    table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        expand=True,
        box=box.MINIMAL,
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Time", style="cyan", width=8, justify="center")
    table.add_column("Type", style="green", width=10, justify="center")
    table.add_column("Content", style="white", no_wrap=False, ratio=1)

    rows: list[tuple[str, str, str]] = []
    from cli.main import format_tool_args  # avoid circular import at module load

    for timestamp, tool_name, args in buffer.tool_calls:
        rows.append((timestamp, "Tool", f"{tool_name}: {format_tool_args(args)}"))
    for timestamp, msg_type, content in buffer.messages:
        s = str(content) if content else ""
        if len(s) > 200:
            s = s[:197] + "..."
        rows.append((timestamp, msg_type, s))

    rows.sort(key=lambda r: r[0], reverse=True)
    if limit is not None:
        rows = rows[:limit]

    for timestamp, msg_type, content in rows:
        table.add_row(timestamp, msg_type, Text(content, overflow="fold"))
    return table


def _format_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def build_stats_text(buffer, stats_handler=None, start_time: float | None = None) -> str:
    completed = sum(1 for s in buffer.agent_status.values() if s == "completed")
    total = len(buffer.agent_status)
    parts = [f"Agents: {completed}/{total}"]

    if stats_handler is not None:
        stats = stats_handler.get_stats()
        parts.append(f"LLM: {stats['llm_calls']}")
        parts.append(f"Tools: {stats['tool_calls']}")
        if stats["tokens_in"] > 0 or stats["tokens_out"] > 0:
            parts.append(
                f"Tokens: {_format_tokens(stats['tokens_in'])}↑ "
                f"{_format_tokens(stats['tokens_out'])}↓"
            )
        else:
            parts.append("Tokens: --")

    parts.append(
        f"Reports: {buffer.get_completed_reports_count()}/{len(buffer.report_sections)}"
    )

    if start_time is not None:
        elapsed = time.time() - start_time
        parts.append(f"⏱ {int(elapsed // 60):02d}:{int(elapsed % 60):02d}")

    return " | ".join(parts)


# --- Textual app --------------------------------------------------------------


class TradingApp(App):
    """Live view with scrollable report and message panes."""

    CSS_PATH = "tui.tcss"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("tab", "focus_next", "Next pane"),
        ("shift+tab", "focus_previous", "Prev pane"),
        ("g", "scroll_top", "Top"),
        ("G", "scroll_bottom", "Bottom"),
    ]

    def __init__(
        self,
        buffer,
        graph,
        init_agent_state: Any,
        graph_args: dict,
        stats_handler,
        start_time: float,
        ticker: str,
        analysis_date: str,
        wall_time_tracker=None,
        on_complete: Callable[[list[Any]], None] | None = None,
    ):
        super().__init__()
        self.buffer = buffer
        self.graph = graph
        self.init_agent_state = init_agent_state
        self.graph_args = graph_args
        self.stats_handler = stats_handler
        self.start_time = start_time
        self.ticker = ticker
        self.analysis_date = analysis_date
        self.wall_time_tracker = wall_time_tracker
        self.on_complete = on_complete
        self.trace: list[Any] = []
        self._stream_error: BaseException | None = None
        self.title = "TradingAgents"
        self.sub_title = f"{ticker} · {analysis_date}"

    # --- composition ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                with VerticalScroll(id="progress-scroll"):
                    yield Static(id="progress")
                with VerticalScroll(id="messages-scroll"):
                    yield Static(id="messages")
            with VerticalScroll(id="report-scroll"):
                yield Markdown("*Waiting for analysis report...*", id="report")
        yield Static(id="footer-stats")
        yield Footer()

    # --- lifecycle -----------------------------------------------------------

    def on_mount(self) -> None:
        self.query_one("#progress-scroll").border_title = "Progress"
        self.query_one("#messages-scroll").border_title = "Messages & Tools"
        self.query_one("#report-scroll").border_title = "Current Report"
        self._refresh_panes()
        self.set_interval(0.25, self._refresh_panes)
        self.run_stream()

    # --- worker --------------------------------------------------------------

    @work(thread=True, exclusive=True)
    def run_stream(self) -> None:
        from cli.main import handle_stream_chunk

        try:
            for chunk in self.graph.graph.stream(
                self.init_agent_state, **self.graph_args
            ):
                handle_stream_chunk(
                    self.buffer, chunk, wall_time_tracker=self.wall_time_tracker
                )
                self.trace.append(chunk)
        except BaseException as exc:  # noqa: BLE001 — re-raised on main thread
            self._stream_error = exc
        finally:
            self.call_from_thread(self._on_stream_done)

    def _on_stream_done(self) -> None:
        if self._stream_error is not None:
            self.buffer.add_message("System", f"Error: {self._stream_error!r}")
            self._refresh_panes()
            return

        # Mark all agents complete and copy final-state report sections back.
        for agent in list(self.buffer.agent_status):
            self.buffer.update_agent_status(agent, "completed")
        self.buffer.add_message(
            "System", f"Completed analysis for {self.analysis_date}"
        )
        if self.wall_time_tracker is not None:
            self.buffer.add_message(
                "System", self.wall_time_tracker.format_summary()
            )
        # Streamed chunks are per-node deltas, not full state — merge them so
        # every report field populated across the run is present (matches the
        # classic renderer).
        final_state: dict = {}
        for chunk in self.trace:
            final_state.update(chunk)
        for section in list(self.buffer.report_sections):
            if section in final_state:
                self.buffer.update_report_section(section, final_state[section])
        self._refresh_panes()
        # Hand control back to the CLI for save/display prompts.
        if self.on_complete is not None:
            self.on_complete(self.trace)
        self.exit()

    # --- rendering -----------------------------------------------------------

    def _refresh_panes(self) -> None:
        self.query_one("#progress", Static).update(build_progress_table(self.buffer))
        self.query_one("#messages", Static).update(
            build_messages_table(self.buffer, limit=None)
        )

        report = self.buffer.current_report
        md = self.query_one("#report", Markdown)
        # Markdown.update is async; fire-and-forget — the next interval will
        # paint over it if a newer report arrives mid-update.
        if report:
            md.update(report)
        self.query_one("#footer-stats", Static).update(
            build_stats_text(self.buffer, self.stats_handler, self.start_time)
        )

    # --- actions -------------------------------------------------------------

    def action_scroll_top(self) -> None:
        focused = self.focused
        if focused is not None:
            scroll = focused if hasattr(focused, "scroll_home") else focused.parent
            if scroll is not None and hasattr(scroll, "scroll_home"):
                scroll.scroll_home(animate=False)

    def action_scroll_bottom(self) -> None:
        focused = self.focused
        if focused is not None:
            scroll = focused if hasattr(focused, "scroll_end") else focused.parent
            if scroll is not None and hasattr(scroll, "scroll_end"):
                scroll.scroll_end(animate=False)
