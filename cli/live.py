"""CLI live display components for the TradingAgents analysis dashboard.

Extracted from cli/main.py to separate concerns:

- **AgentStatusTracker** — agent execution state machine
- **MessageStore** — message and tool-call storage with deduplication
- **ReportBuilder** — report section management and final-report assembly
- **DisplayManager** — Rich-powered TUI layout and panel construction
"""

import time
from collections import deque
from datetime import datetime

from rich import box
from rich.layout import Layout
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from tradingagents.graph.analyst_execution import sync_analyst_tracker_from_chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_tokens(n: int) -> str:
    """Format token count for display (e.g. 1500 -> '1.5k')."""
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def format_tool_args(args, max_length: int = 80) -> str:
    """Format tool arguments for terminal display, truncating if needed."""
    result = str(args)
    if len(result) > max_length:
        return result[:max_length - 3] + "..."
    return result


# ---------------------------------------------------------------------------
# AgentStatusTracker
# ---------------------------------------------------------------------------

class AgentStatusTracker:
    """Tracks the execution status of every agent in the analysis pipeline.

    Holds the state-machine logic that decides which agent is pending,
    in-progress, or completed based on the streamed analysis chunks.
    """

    # Ordered list of analysts for deterministic status transitions.
    ANALYST_ORDER = ["market", "social", "news", "fundamentals"]

    ANALYST_AGENT_NAMES = {
        "market": "Market Analyst",
        "social": "Sentiment Analyst",
        "news": "News Analyst",
        "fundamentals": "Fundamentals Analyst",
    }

    ANALYST_REPORT_MAP = {
        "market": "market_report",
        "social": "sentiment_report",
        "news": "news_report",
        "fundamentals": "fundamentals_report",
    }

    ANALYST_MAPPING = {
        "market": "Market Analyst",
        "social": "Sentiment Analyst",
        "news": "News Analyst",
        "fundamentals": "Fundamentals Analyst",
    }

    # Teams that always execute (not user-selectable).
    FIXED_AGENTS = {
        "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
        "Trading Team": ["Trader"],
        "Risk Management": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
        "Portfolio Management": ["Portfolio Manager"],
    }

    def __init__(self):
        self.agent_status: dict[str, str] = {}
        self.selected_analysts: list[str] = []
        self.current_agent: str | None = None

    # ---- Initialization ----

    def init_for_analysis(self, selected_analysts: list[str]):
        """Build the initial agent-status dict from the user's analyst choices."""
        self.selected_analysts = [a.lower() for a in selected_analysts]
        self.agent_status = {}

        for analyst_key in self.selected_analysts:
            if analyst_key in self.ANALYST_MAPPING:
                self.agent_status[self.ANALYST_MAPPING[analyst_key]] = "pending"

        for team_agents in self.FIXED_AGENTS.values():
            for agent in team_agents:
                self.agent_status[agent] = "pending"

        self.current_agent = None

    # ---- Status mutations ----

    def update_status(self, agent: str, status: str):
        """Set an agent's status. Silently ignored when the agent is unknown."""
        if agent in self.agent_status:
            self.agent_status[agent] = status
            self.current_agent = agent

    def set_all_completed(self):
        """Mark every known agent as completed."""
        for agent in self.agent_status:
            self.agent_status[agent] = "completed"

    def mark_research_team_in_progress(self):
        """Transition all three research-team agents to in_progress."""
        for agent in ("Bull Researcher", "Bear Researcher", "Research Manager"):
            self.update_status(agent, "in_progress")

    # ---- Queries ----

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.agent_status.values() if s == "completed")

    @property
    def total_count(self) -> int:
        return len(self.agent_status)

    # ---- Stream-driven analyst state machine ----

    def update_from_analyst_stream(self, chunk: dict, report_builder: "ReportBuilder",
                                   wall_time_tracker=None):
        """Advance analyst statuses based on a new stream chunk.

        Logic
        -----
        * Analysts whose ``report_key`` has content → ``completed``.
        * First analyst without content → ``in_progress``.
        * Remaining analysts → ``pending``.
        * When every selected analyst is done → Bull Researcher → ``in_progress``.
        """
        selected = self.selected_analysts
        found_active = False

        if wall_time_tracker is not None:
            sync_analyst_tracker_from_chunk(wall_time_tracker, chunk)

        for analyst_key in self.ANALYST_ORDER:
            if analyst_key not in selected:
                continue

            agent_name = self.ANALYST_AGENT_NAMES[analyst_key]
            report_key = self.ANALYST_REPORT_MAP[analyst_key]

            if chunk.get(report_key):
                report_builder.update_section(report_key, chunk[report_key])

            has_report = bool(report_builder.report_sections.get(report_key))

            if has_report:
                self.update_status(agent_name, "completed")
            elif not found_active:
                self.update_status(agent_name, "in_progress")
                found_active = True
            else:
                self.update_status(agent_name, "pending")

        if (not found_active and selected
                and self.agent_status.get("Bull Researcher") == "pending"):
            self.update_status("Bull Researcher", "in_progress")


# ---------------------------------------------------------------------------
# MessageStore
# ---------------------------------------------------------------------------

class MessageStore:
    """Thread-safe-ish storage for log messages and tool calls with dedup."""

    def __init__(self, max_length: int = 100):
        self.messages: deque = deque(maxlen=max_length)
        self.tool_calls: deque = deque(maxlen=max_length)
        self._processed_message_ids: set[str] = set()

    def add_message(self, message_type: str, content: str):
        """Append a timestamped message entry."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.messages.append((timestamp, message_type, content))

    def add_tool_call(self, tool_name: str, args: dict):
        """Append a timestamped tool-call entry."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.tool_calls.append((timestamp, tool_name, args))

    def is_duplicate(self, msg_id: str) -> bool:
        return msg_id in self._processed_message_ids

    def mark_processed(self, msg_id: str):
        self._processed_message_ids.add(msg_id)

    def clear(self):
        self.messages.clear()
        self.tool_calls.clear()
        self._processed_message_ids.clear()


# ---------------------------------------------------------------------------
# ReportBuilder
# ---------------------------------------------------------------------------

class ReportBuilder:
    """Assembles per-section reports and the consolidated final report.

    Each section maps to a ``(analyst_key, finalizing_agent)`` pair so the
    builder can count how many sections are *fully completed* (content exists
    **and** the finalizing agent has run).
    """

    REPORT_SECTIONS: dict[str, tuple[str | None, str]] = {
        "market_report":         ("market", "Market Analyst"),
        "sentiment_report":      ("social", "Sentiment Analyst"),
        "news_report":           ("news", "News Analyst"),
        "fundamentals_report":   ("fundamentals", "Fundamentals Analyst"),
        "investment_plan":        (None, "Research Manager"),
        "trader_investment_plan": (None, "Trader"),
        "final_trade_decision":   (None, "Portfolio Manager"),
    }

    SECTION_TITLES = {
        "market_report":         "Market Analysis",
        "sentiment_report":      "Social Sentiment",
        "news_report":           "News Analysis",
        "fundamentals_report":   "Fundamentals Analysis",
        "investment_plan":        "Research Team Decision",
        "trader_investment_plan": "Trading Team Plan",
        "final_trade_decision":   "Portfolio Management Decision",
    }

    def __init__(self):
        self.report_sections: dict[str, str | None] = {}
        self.current_report: str | None = None
        self.final_report: str | None = None
        self.selected_analysts: list[str] = []

    def init_for_analysis(self, selected_analysts: list[str]):
        """Reset sections for a new analysis run."""
        self.selected_analysts = [a.lower() for a in selected_analysts]
        self.report_sections = {}
        for section, (analyst_key, _) in self.REPORT_SECTIONS.items():
            if analyst_key is None or analyst_key in self.selected_analysts:
                self.report_sections[section] = None
        self.current_report = None
        self.final_report = None

    # ---- Section updates ----

    def update_section(self, section_name: str, content: str):
        """Store new content for *section_name* and rebuild derived reports."""
        if section_name not in self.report_sections:
            return
        self.report_sections[section_name] = content
        self._rebuild_current_report()
        self._rebuild_final_report()

    def _rebuild_current_report(self):
        """Set ``current_report`` to the most-recently-updated section."""
        latest_section = None
        latest_content = None
        for section, content in self.report_sections.items():
            if content is not None:
                latest_section = section
                latest_content = content
        if latest_section and latest_content:
            self.current_report = (
                f"### {self.SECTION_TITLES[latest_section]}\n{latest_content}"
            )

    def _rebuild_final_report(self):
        """Assemble the complete multi-section final report markdown."""
        parts = []

        # I. Analyst Team
        analyst_keys = ["market_report", "sentiment_report",
                        "news_report", "fundamentals_report"]
        if any(self.report_sections.get(s) for s in analyst_keys):
            parts.append("## Analyst Team Reports")
            for key in analyst_keys:
                content = self.report_sections.get(key)
                if content:
                    parts.append(f"### {self.SECTION_TITLES[key]}\n{content}")

        # II. Research Team
        if self.report_sections.get("investment_plan"):
            parts.append("## Research Team Decision")
            parts.append(str(self.report_sections["investment_plan"]))

        # III. Trading Team
        if self.report_sections.get("trader_investment_plan"):
            parts.append("## Trading Team Plan")
            parts.append(str(self.report_sections["trader_investment_plan"]))

        # IV. Portfolio Management
        if self.report_sections.get("final_trade_decision"):
            parts.append("## Portfolio Management Decision")
            parts.append(str(self.report_sections["final_trade_decision"]))

        self.final_report = "\n\n".join(parts) if parts else None

    # ---- Completion query ----

    def get_completed_count(self, agent_tracker: AgentStatusTracker) -> int:
        """Count sections whose content exists *and* finalizing agent completed."""
        count = 0
        for section in self.report_sections:
            if section not in self.REPORT_SECTIONS:
                continue
            _, finalizing_agent = self.REPORT_SECTIONS[section]
            has_content = self.report_sections.get(section) is not None
            agent_done = agent_tracker.agent_status.get(finalizing_agent) == "completed"
            if has_content and agent_done:
                count += 1
        return count


# ---------------------------------------------------------------------------
# DisplayManager
# ---------------------------------------------------------------------------

class DisplayManager:
    """Constructs and updates the Rich live TUI layout."""

    ALL_TEAMS = {
        "Analyst Team": [
            "Market Analyst", "Sentiment Analyst",
            "News Analyst", "Fundamentals Analyst",
        ],
        "Research Team": [
            "Bull Researcher", "Bear Researcher", "Research Manager",
        ],
        "Trading Team": ["Trader"],
        "Risk Management": [
            "Aggressive Analyst", "Neutral Analyst", "Conservative Analyst",
        ],
        "Portfolio Management": ["Portfolio Manager"],
    }

    def __init__(self, refresh_per_second: int = 4):
        self.layout: Layout | None = None
        self.refresh_per_second = refresh_per_second

    # ---- Layout ----

    def create_layout(self) -> Layout:
        """Build the three-row layout: header / main / footer."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )
        layout["main"].split_column(
            Layout(name="upper", ratio=3),
            Layout(name="analysis", ratio=5),
        )
        layout["upper"].split_row(
            Layout(name="progress", ratio=2),
            Layout(name="messages", ratio=3),
        )
        self.layout = layout
        return layout

    # ---- Panel builders ----

    def _build_header(self) -> Panel:
        return Panel(
            "[bold green]Welcome to TradingAgents CLI[/bold green]\n"
            "[dim]© [Tauric Research](https://github.com/TauricResearch)[/dim]",
            title="Welcome to TradingAgents",
            border_style="green",
            padding=(1, 2),
            expand=True,
        )

    def _build_progress_panel(self, agent_status: dict[str, str]) -> Panel:
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
        for team, agents in self.ALL_TEAMS.items():
            active = [a for a in agents if a in agent_status]
            if active:
                teams[team] = active

        for team, agents in teams.items():
            first = agents[0]
            table.add_row(team, first, self._format_status_cell(agent_status.get(first, "pending")))
            for agent in agents[1:]:
                table.add_row("", agent, self._format_status_cell(agent_status.get(agent, "pending")))
            table.add_row("─" * 20, "─" * 20, "─" * 20, style="dim")

        return Panel(table, title="Progress", border_style="cyan", padding=(1, 2))

    @staticmethod
    def _format_status_cell(status: str):
        if status == "in_progress":
            return Spinner("dots", text="[blue]in_progress[/blue]", style="bold cyan")
        color = {"pending": "yellow", "completed": "green", "error": "red"}.get(status, "white")
        return f"[{color}]{status}[/{color}]"

    def _build_messages_panel(self, message_store: MessageStore) -> Panel:
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

        entries: list[tuple[str, str, str]] = []
        for ts, name, args in message_store.tool_calls:
            entries.append((ts, "Tool", f"{name}: {format_tool_args(args)}"))
        for ts, msg_type, content in message_store.messages:
            text = str(content)[:197] + "..." if content and len(str(content)) > 200 else str(content or "")
            entries.append((ts, msg_type, text))
        entries.sort(key=lambda x: x[0], reverse=True)

        for ts, typ, text in entries[:12]:
            table.add_row(ts, typ, Text(text, overflow="fold"))

        return Panel(table, title="Messages & Tools", border_style="blue", padding=(1, 2))

    @staticmethod
    def _build_analysis_panel(current_report: str | None) -> Panel:
        if current_report:
            return Panel(Markdown(current_report), title="Current Report",
                          border_style="green", padding=(1, 2))
        return Panel("[italic]Waiting for analysis report...[/italic]",
                      title="Current Report", border_style="green", padding=(1, 2))

    def _build_footer(self, agent_tracker: AgentStatusTracker,
                      report_builder: ReportBuilder,
                      stats_handler=None, start_time: float | None = None) -> Panel:
        parts = [f"Agents: {agent_tracker.completed_count}/{agent_tracker.total_count}"]

        if stats_handler:
            stats = stats_handler.get_stats()
            parts.append(f"LLM: {stats['llm_calls']}")
            parts.append(f"Tools: {stats['tool_calls']}")
            if stats["tokens_in"] > 0 or stats["tokens_out"] > 0:
                parts.append(
                    f"Tokens: {format_tokens(stats['tokens_in'])}↑ "
                    f"{format_tokens(stats['tokens_out'])}↓"
                )
            else:
                parts.append("Tokens: --")

        reports_c = report_builder.get_completed_count(agent_tracker)
        reports_t = len(report_builder.report_sections)
        parts.append(f"Reports: {reports_c}/{reports_t}")

        if start_time:
            elapsed = time.time() - start_time
            parts.append(f"⏱ {int(elapsed // 60):02d}:{int(elapsed % 60):02d}")

        table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
        table.add_column("Stats", justify="center")
        table.add_row(" | ".join(parts))
        return Panel(table, border_style="grey50")

    # ---- Full update ----

    def update_all(self, agent_tracker: AgentStatusTracker,
                   message_store: MessageStore,
                   report_builder: ReportBuilder,
                   stats_handler=None, start_time: float | None = None):
        """Refresh every panel in the layout from current component state."""
        if self.layout is None:
            self.create_layout()

        self.layout["header"].update(self._build_header())
        self.layout["progress"].update(
            self._build_progress_panel(agent_tracker.agent_status))
        self.layout["messages"].update(self._build_messages_panel(message_store))
        self.layout["analysis"].update(
            self._build_analysis_panel(report_builder.current_report))
        self.layout["footer"].update(
            self._build_footer(agent_tracker, report_builder,
                               stats_handler, start_time))
