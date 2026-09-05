import datetime
import os
import queue
import sys
import threading
import time
from collections import deque
from functools import wraps
from pathlib import Path

# Agent/LLM output is full of unicode (⏱, arrows, markdown). On Windows the
# console defaults to cp1252, which turns such prints into UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
from rich import box
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from cli.announcements import display_announcements, fetch_announcements
from cli.dashboard import start_dashboard, stop_dashboard
from cli.stats_handler import StatsCallbackHandler
from cli.utils import (
    ask_anthropic_effort,
    ask_gemini_thinking_config,
    ask_glm_region,
    ask_minimax_region,
    ask_nvidia_reasoning_effort,
    ask_openai_reasoning_effort,
    ask_opencode_endpoint,
    ask_output_language,
    ask_qwen_region,
    confirm_ollama_endpoint,
    detect_asset_type,
    ensure_api_key,
    get_ticker,
    prompt_openai_compatible_url,
    resolve_backend_url,
    select_analysts,
    select_deep_thinking_agent,
    select_llm_provider,
    select_research_depth,
    select_shallow_thinking_agent,
    select_table_model,
)
from cli.utils import BACK_SENTINEL
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import (
    AnalystWallTimeTracker,
    build_analyst_execution_plan,
    get_initial_analyst_node,
    sync_analyst_tracker_from_chunk,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree

console = Console()

# prompt_toolkit's win32 output module is importable only on Windows (it asserts
# the platform at import time), so gate on the platform rather than catching the
# failure — that way a genuinely broken prompt_toolkit on Windows still surfaces
# instead of silently disabling the handler below. Off Windows this stays an
# empty tuple, which `except` accepts and never matches (#1138).
if sys.platform == "win32":  # pragma: no cover - platform dependent
    from prompt_toolkit.output.win32 import NoConsoleScreenBufferError

    _NO_CONSOLE_ERRORS: tuple[type[BaseException], ...] = (NoConsoleScreenBufferError,)
else:
    _NO_CONSOLE_ERRORS = ()

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents CLI: Multi-Agents LLM Financial Trading Framework",
    add_completion=True,  # Enable shell completion
)


# Create a deque to store recent messages with a maximum length
class MessageBuffer:
    # Fixed teams that always run (not user-selectable)
    FIXED_AGENTS = {
        "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
        "Trading Team": ["Trader"],
        "Risk Management": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
        "Portfolio Management": ["Portfolio Manager"],
    }

    # Analyst name mapping
    ANALYST_MAPPING = {
        "market": "Market Analyst",
        "social": "Sentiment Analyst",
        "news": "News Analyst",
        "fundamentals": "Fundamentals Analyst",
    }

    # Report section mapping: section -> (analyst_key for filtering, finalizing_agent)
    # analyst_key: which analyst selection controls this section (None = always included)
    # finalizing_agent: which agent must be "completed" for this report to count as done
    REPORT_SECTIONS = {
        "market_report": ("market", "Market Analyst"),
        "sentiment_report": ("social", "Sentiment Analyst"),
        "news_report": ("news", "News Analyst"),
        "fundamentals_report": ("fundamentals", "Fundamentals Analyst"),
        "investment_plan": (None, "Research Manager"),
        "trader_investment_plan": (None, "Trader"),
        "final_trade_decision": (None, "Portfolio Manager"),
    }

    def __init__(self, max_length=300):
        self.messages = deque(maxlen=max_length)
        self.tool_calls = deque(maxlen=max_length)
        self.current_report = None
        self.final_report = None  # Store the complete final report
        self.agent_status = {}
        self.current_agent = None
        self.report_sections = {}
        self.selected_analysts = []
        self._processed_message_ids = set()
        self.last_update = time.time()  # heartbeat: last message/tool/status/report event

    def init_for_analysis(self, selected_analysts):
        """Initialize agent status and report sections based on selected analysts.

        Args:
            selected_analysts: List of analyst type strings (e.g., ["market", "news"])
        """
        self.selected_analysts = [a.lower() for a in selected_analysts]

        # Build agent_status dynamically
        self.agent_status = {}

        # Add selected analysts
        for analyst_key in self.selected_analysts:
            if analyst_key in self.ANALYST_MAPPING:
                self.agent_status[self.ANALYST_MAPPING[analyst_key]] = "pending"

        # Add fixed teams
        for team_agents in self.FIXED_AGENTS.values():
            for agent in team_agents:
                self.agent_status[agent] = "pending"

        # Build report_sections dynamically
        self.report_sections = {}
        for section, (analyst_key, _) in self.REPORT_SECTIONS.items():
            if analyst_key is None or analyst_key in self.selected_analysts:
                self.report_sections[section] = None

        # Reset other state
        self.current_report = None
        self.final_report = None
        self.current_agent = None
        self.messages.clear()
        self.tool_calls.clear()
        self._processed_message_ids.clear()
        self._touch()

    def get_completed_reports_count(self):
        """Count reports that are finalized (their finalizing agent is completed).

        A report is considered complete when:
        1. The report section has content (not None), AND
        2. The agent responsible for finalizing that report has status "completed"

        This prevents interim updates (like debate rounds) from counting as completed.
        """
        count = 0
        for section in self.report_sections:
            if section not in self.REPORT_SECTIONS:
                continue
            _, finalizing_agent = self.REPORT_SECTIONS[section]
            # Report is complete if it has content AND its finalizing agent is done
            has_content = self.report_sections.get(section) is not None
            agent_done = self.agent_status.get(finalizing_agent) == "completed"
            if has_content and agent_done:
                count += 1
        return count

    def _touch(self):
        self.last_update = time.time()

    def last_activity_age(self) -> int:
        """Seconds since the last agent event (message/tool/status/report)."""
        try:
            return max(0, int(time.time() - self.last_update))
        except Exception:
            return 0

    def add_message(self, message_type, content):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.messages.append((timestamp, message_type, content))
        self._touch()

    def add_tool_call(self, tool_name, args):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.tool_calls.append((timestamp, tool_name, args))
        self._touch()

    def update_agent_status(self, agent, status):
        if agent in self.agent_status:
            self.agent_status[agent] = status
            self.current_agent = agent
            self._touch()

    def update_report_section(self, section_name, content):
        if section_name in self.report_sections:
            self.report_sections[section_name] = content
            self._update_current_report()
            self._touch()

    def _update_current_report(self):
        # For the panel display, only show the most recently updated section
        latest_section = None
        latest_content = None

        # Find the most recently updated section
        for section, content in self.report_sections.items():
            if content is not None:
                latest_section = section
                latest_content = content

        if latest_section and latest_content:
            # Format the current section for display
            section_titles = {
                "market_report": "Market Analysis",
                "sentiment_report": "Social Sentiment",
                "news_report": "News Analysis",
                "fundamentals_report": "Fundamentals Analysis",
                "investment_plan": "Research Team Decision",
                "trader_investment_plan": "Trading Team Plan",
                "final_trade_decision": "Portfolio Management Decision",
            }
            self.current_report = (
                f"### {section_titles[latest_section]}\n{latest_content}"
            )

        # Update the final complete report
        self._update_final_report()

    def _update_final_report(self):
        report_parts = []

        # Analyst Team Reports - use .get() to handle missing sections
        analyst_sections = ["market_report", "sentiment_report", "news_report", "fundamentals_report"]
        if any(self.report_sections.get(section) for section in analyst_sections):
            report_parts.append("## Analyst Team Reports")
            if self.report_sections.get("market_report"):
                report_parts.append(
                    f"### Market Analysis\n{self.report_sections['market_report']}"
                )
            if self.report_sections.get("sentiment_report"):
                report_parts.append(
                    f"### Social Sentiment\n{self.report_sections['sentiment_report']}"
                )
            if self.report_sections.get("news_report"):
                report_parts.append(
                    f"### News Analysis\n{self.report_sections['news_report']}"
                )
            if self.report_sections.get("fundamentals_report"):
                report_parts.append(
                    f"### Fundamentals Analysis\n{self.report_sections['fundamentals_report']}"
                )

        # Research Team Reports
        if self.report_sections.get("investment_plan"):
            report_parts.append("## Research Team Decision")
            report_parts.append(f"{self.report_sections['investment_plan']}")

        # Trading Team Reports
        if self.report_sections.get("trader_investment_plan"):
            report_parts.append("## Trading Team Plan")
            report_parts.append(f"{self.report_sections['trader_investment_plan']}")

        # Portfolio Management Decision
        if self.report_sections.get("final_trade_decision"):
            report_parts.append("## Portfolio Management Decision")
            report_parts.append(f"{self.report_sections['final_trade_decision']}")

        self.final_report = "\n\n".join(report_parts) if report_parts else None


message_buffer = MessageBuffer()

# Scroll state for independent panel scrolling
class ScrollState:
    def __init__(self):
        self.progress_offset = 0
        self.messages_offset = 0
        self.analysis_offset = 0

scroll_state = ScrollState()

# Port of the auto-started web dashboard (None = disabled/unavailable).
# Shown in the footer so the URL survives Rich's fullscreen takeover.
dashboard_port = None

# Single background stdin reader feeding ask_everywhere(). One daemon thread
# for the whole process: it survives CLI restarts, so repeated runs never
# leak blocked input threads.
_console_lines: queue.Queue = queue.Queue()
_console_reader_started = False


def _ensure_console_reader():
    global _console_reader_started
    if _console_reader_started:
        return

    def _read_loop():
        while True:
            try:
                line = sys.stdin.readline()
            except Exception:
                return
            if line == "":
                return  # EOF
            _console_lines.put(line.rstrip("\r\n"))

    threading.Thread(target=_read_loop, daemon=True).start()
    _console_reader_started = True


def ask_everywhere(server, question, default=""):
    """Ask in the terminal AND on the web dashboard; first answer wins.

    The question is printed to the console and simultaneously published to
    the dashboard's prompt bar (if a dashboard server is running). Whichever
    side answers first wins; the other side's pending state is cleared.
    Ctrl-C still aborts to the caller. Empty input returns "" (callers map
    that to the default, mirroring typer.prompt behavior).
    """
    pending = getattr(server, "pending_prompt", None) if server is not None else None
    if pending is not None:
        pending["question"] = question
        pending["default"] = default
        pending["answer"] = None
    # Drop keystrokes typed earlier (e.g. during the Live view) so a stale
    # line can't auto-answer the fresh prompt.
    while True:
        try:
            _console_lines.get_nowait()
        except queue.Empty:
            break
    _ensure_console_reader()
    console.print(f"{question} [{default}]: ", end="")
    try:
        while True:
            if pending is not None and pending.get("answer") is not None:
                return pending["answer"]
            try:
                return _console_lines.get_nowait()
            except queue.Empty:
                pass
            time.sleep(0.2)
    finally:
        if pending is not None:
            pending["question"] = None
            pending["default"] = None
            pending["answer"] = None


def create_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3),
    )
    layout["main"].split_column(
        Layout(name="upper", ratio=3), Layout(name="analysis", ratio=5)
    )
    layout["upper"].split_row(
        Layout(name="progress", ratio=2), Layout(name="messages", ratio=3)
    )
    return layout


def format_tokens(n):
    """Format token count for display."""
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def update_display(layout, spinner_text=None, stats_handler=None, start_time=None):
    # Header with welcome message
    layout["header"].update(
        Panel(
            "[bold green]Welcome to TradingAgents CLI[/bold green]\n"
            "[dim]© [Tauric Research](https://github.com/TauricResearch)[/dim]",
            title="Welcome to TradingAgents",
            border_style="green",
            padding=(1, 2),
            expand=True,
        )
    )

    # Progress panel showing agent status
    progress_table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        box=box.SIMPLE_HEAD,  # Use simple header with horizontal lines
        title=None,  # Remove the redundant Progress title
        padding=(0, 2),  # Add horizontal padding
        expand=True,  # Make table expand to fill available space
    )
    progress_table.add_column("Team", style="cyan", justify="center", width=20)
    progress_table.add_column("Agent", style="green", justify="center", width=20)
    progress_table.add_column("Status", style="yellow", justify="center", width=20)

    # Group agents by team - filter to only include agents in agent_status
    all_teams = {
        "Analyst Team": [
            "Market Analyst",
            "Sentiment Analyst",
            "News Analyst",
            "Fundamentals Analyst",
        ],
        "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
        "Trading Team": ["Trader"],
        "Risk Management": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
        "Portfolio Management": ["Portfolio Manager"],
    }

    # Filter teams to only include agents that are in agent_status
    teams = {}
    for team, agents in all_teams.items():
        active_agents = [a for a in agents if a in message_buffer.agent_status]
        if active_agents:
            teams[team] = active_agents

    # Convert teams dict to list of items for scrolling
    teams_items = list(teams.items())
    
    # Calculate how many teams we can show based on available space
    max_teams = 8  # Approximate number of teams that fit in the panel
    
    # Get teams based on scroll offset
    start_idx = scroll_state.progress_offset
    end_idx = start_idx + max_teams
    visible_teams = teams_items[start_idx:end_idx]
    
    # Add scroll indicators if needed
    if len(teams_items) > end_idx:
        # Add a visual indicator that more teams are available
        visible_teams.append(("__SCROLL_DOWN__", [f"[dim]... and {len(teams_items) - end_idx} more teams (scroll right)[/dim]"]))
    elif start_idx > 0:
        # Add a visual indicator that earlier teams are available
        visible_teams.insert(0, ("__SCROLL_UP__", [f"[dim]... and {start_idx} earlier teams (scroll left)[/dim]"]))

    for team, agents in visible_teams:
        # Skip scroll indicator rows
        if team.startswith("__SCROLL_"):
            progress_table.add_row("", "", team)
            continue
        # Add first agent with team name
        first_agent = agents[0]
        status = message_buffer.agent_status.get(first_agent, "pending")
        if status == "in_progress":
            spinner = Spinner(
                "dots", text="[blue]in_progress[/blue]", style="bold cyan"
            )
            status_cell = spinner
        else:
            status_color = {
                "pending": "yellow",
                "completed": "green",
                "error": "red",
            }.get(status, "white")
            status_cell = f"[{status_color}]{status}[/{status_color}]"
        progress_table.add_row(team, first_agent, status_cell)

        # Add remaining agents in team
        for agent in agents[1:]:
            status = message_buffer.agent_status.get(agent, "pending")
            if status == "in_progress":
                spinner = Spinner(
                    "dots", text="[blue]in_progress[/blue]", style="bold cyan"
                )
                status_cell = spinner
            else:
                status_color = {
                    "pending": "yellow",
                    "completed": "green",
                    "error": "red",
                }.get(status, "white")
                status_cell = f"[{status_color}]{status}[/{status_color}]"
            progress_table.add_row("", agent, status_cell)

        # Add horizontal line after each team
        progress_table.add_row("─" * 20, "─" * 20, "─" * 20, style="dim")

    layout["progress"].update(
        Panel(progress_table, title="Progress", border_style="cyan", padding=(1, 2))
    )

    # Messages panel showing recent messages and tool calls
    messages_table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        expand=True,  # Make table expand to fill available space
        box=box.MINIMAL,  # Use minimal box style for a lighter look
        show_lines=True,  # Keep horizontal lines
        padding=(0, 1),  # Add some padding between columns
    )
    messages_table.add_column("Time", style="cyan", width=8, justify="center")
    messages_table.add_column("Type", style="green", width=10, justify="center")
    messages_table.add_column(
        "Content", style="white", no_wrap=False, ratio=1
    )  # Make content column expand

    # Combine tool calls and messages
    all_messages = []

    # Add tool calls
    for timestamp, tool_name, args in message_buffer.tool_calls:
        formatted_args = format_tool_args(args)
        all_messages.append((timestamp, "Tool", f"{tool_name}: {formatted_args}"))

    # Add regular messages
    for timestamp, msg_type, content in message_buffer.messages:
        content_str = str(content) if content else ""
        if len(content_str) > 500:
            content_str = content_str[:497] + "..."
        all_messages.append((timestamp, msg_type, content_str))

    # Sort by timestamp descending (newest first)
    all_messages.sort(key=lambda x: x[0], reverse=True)

    # Calculate how many messages we can show based on available space
    max_messages = 12

    # Get messages based on scroll offset
    start_idx = scroll_state.messages_offset
    end_idx = start_idx + max_messages
    recent_messages = all_messages[start_idx:end_idx]
    
    # Add messages to table (already in newest-first order)
    for timestamp, msg_type, content in recent_messages:
        # Format content with word wrapping
        wrapped_content = Text(content, overflow="fold")
        messages_table.add_row(timestamp, msg_type, wrapped_content)

    layout["messages"].update(
        Panel(
            messages_table,
            title="Messages & Tools",
            border_style="blue",
            padding=(1, 2),
        )
    )

    # Analysis panel showing current report
    if message_buffer.current_report:
        # Split report into lines for scrolling
        report_lines = message_buffer.current_report.split('\n')
        
        # Calculate how many lines we can show based on available space
        # Estimate based on panel height (roughly 20-30 lines for typical terminal)
        max_report_lines = 25
        
        # Get report lines based on scroll offset
        start_idx = scroll_state.analysis_offset
        end_idx = start_idx + max_report_lines
        visible_lines = report_lines[start_idx:end_idx]
        
        # Add scroll indicators if needed
        if len(report_lines) > end_idx:
            # Add a visual indicator that more lines are available
            visible_lines.append(f"[dim]... and {len(report_lines) - end_idx} more lines (scroll Page Down)[/dim]")
        elif start_idx > 0:
            # Add a visual indicator that earlier lines are available
            visible_lines.insert(0, f"[dim]... and {start_idx} earlier lines (scroll Page Up)[/dim]")
        
        # Join the visible lines back together
        visible_report = '\n'.join(visible_lines)
        
        layout["analysis"].update(
            Panel(
                Markdown(visible_report),
                title="Current Report",
                border_style="green",
                padding=(1, 2),
            )
        )
    else:
        layout["analysis"].update(
            Panel(
                "[italic]Waiting for analysis report...[/italic]",
                title="Current Report",
                border_style="green",
                padding=(1, 2),
            )
        )

    # Footer with statistics
    # Agent progress - derived from agent_status dict
    agents_completed = sum(
        1 for status in message_buffer.agent_status.values() if status == "completed"
    )
    agents_total = len(message_buffer.agent_status)

    # Report progress - based on agent completion (not just content existence)
    reports_completed = message_buffer.get_completed_reports_count()
    reports_total = len(message_buffer.report_sections)

    # Build stats parts
    stats_parts = [f"Agents: {agents_completed}/{agents_total}"]

    # LLM and tool stats from callback handler
    if stats_handler:
        stats = stats_handler.get_stats()
        stats_parts.append(f"LLM: {stats['llm_calls']}")
        stats_parts.append(f"Tools: {stats['tool_calls']}")

        # Token display with graceful fallback
        if stats["tokens_in"] > 0 or stats["tokens_out"] > 0:
            tokens_str = f"Tokens: {format_tokens(stats['tokens_in'])}\u2191 {format_tokens(stats['tokens_out'])}\u2193"
        else:
            tokens_str = "Tokens: --"
        stats_parts.append(tokens_str)

    stats_parts.append(f"Reports: {reports_completed}/{reports_total}")
    if dashboard_port:
        stats_parts.append(f"Web :{dashboard_port}")

    # Elapsed time
    if start_time:
        elapsed = time.time() - start_time
        elapsed_str = f"\u23f1 {int(elapsed // 60):02d}:{int(elapsed % 60):02d}"
        stats_parts.append(elapsed_str)

    # Live-activity heartbeat: which agent last did anything, and how long
    # ago — so the terminal view never looks frozen during long LLM calls.
    try:
        _age = message_buffer.last_activity_age()
        _agent = message_buffer.current_agent or "idle"
        stats_parts.append(f"\u25cf {_agent} {_age}s ago")
    except Exception:
        pass

    stats_table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
    stats_table.add_column("Stats", justify="center")
    stats_table.add_row(" | ".join(stats_parts))

    layout["footer"].update(Panel(stats_table, border_style="grey50"))


def get_user_selections():
    """Get all user selections before starting the analysis display."""
    # Display ASCII art welcome message
    with open(Path(__file__).parent / "static" / "welcome.txt", encoding="utf-8") as f:
        welcome_ascii = f.read()

    # Create welcome box content
    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgents: Multi-Agents LLM Financial Trading Framework - CLI[/bold green]\n\n"
    welcome_content += "[bold]Workflow Steps:[/bold]\n"
    welcome_content += "I. Analyst Team → II. Research Team → III. Trader → IV. Risk Management → V. Portfolio Management\n\n"
    welcome_content += (
        "[dim]Built by [Tauric Research](https://github.com/TauricResearch)[/dim]"
    )

    # Create and center the welcome box
    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="Welcome to TradingAgents",
        subtitle="Multi-Agents LLM Financial Trading Framework",
    )
    console.print(Align.center(welcome_box))
    console.print()
    console.print()  # Add vertical space before announcements

    # Fetch and display announcements (silent on failure)
    announcements = fetch_announcements()
    display_announcements(console, announcements)

    # Create a boxed questionnaire for each step
    def create_question_box(title, prompt, default=None):
        box_content = f"[bold]{title}[/bold]\n"
        box_content += f"[dim]{prompt}[/dim]"
        if default:
            box_content += f"\n[dim]Default: {default}[/dim]"
        return Panel(box_content, border_style="blue", padding=(1, 2))

    def thinking_value_or_prompt(env_var, config_key, label, box_title, box_body, prompt_fn):
        """Return the env-configured reasoning/thinking value, or prompt for it.

        When ``env_var`` is set the interactive choice is skipped and the value
        the env overlay placed on DEFAULT_CONFIG is used — mirroring the
        env-precedence rule applied to the other selection steps.
        """
        if os.environ.get(env_var):
            value = DEFAULT_CONFIG[config_key]
            console.print(f"[green]✓ {label} from environment:[/green] {value}")
            return value
        console.print(create_question_box(box_title, box_body))
        return prompt_fn()

    # Step 1: Ticker symbol
    console.print(
        create_question_box(
            "Step 1: Ticker Symbol",
            "Enter the ticker, with exchange suffix when needed (e.g. SPY, 0700.HK, BTC-USD)",
            "SPY",
        )
    )
    selected_ticker = get_ticker()
    asset_type = detect_asset_type(selected_ticker)
    # Only announce when it's not the default stock path, to avoid printing
    # "stock" on every run.
    if asset_type.value != "stock":
        console.print(
            f"[green]Detected asset type:[/green] {asset_type.value}"
        )

    # Step 2: Analysis date
    default_date = datetime.datetime.now().strftime("%Y-%m-%d")
    console.print(
        create_question_box(
            "Step 2: Analysis Date",
            "Enter the analysis date (YYYY-MM-DD)",
            default_date,
        )
    )
    analysis_date = get_analysis_date(selected_ticker)

    # Step 3: Output language (skipped when set via TRADINGAGENTS_OUTPUT_LANGUAGE)
    if os.environ.get("TRADINGAGENTS_OUTPUT_LANGUAGE"):
        output_language = DEFAULT_CONFIG["output_language"]
        console.print(
            f"[green]✓ Output language from environment:[/green] {output_language}"
        )
    else:
        console.print(
            create_question_box(
                "Step 3: Output Language",
                "Select the language for analyst reports and final decision"
            )
        )
        output_language = ask_output_language()

    # Step 4: Select analysts
    console.print(
        create_question_box(
            "Step 4: Analysts Team", "Select your LLM analyst agents for the analysis"
        )
    )
    selected_analysts = select_analysts(asset_type)
    console.print(
        f"[green]Selected analysts:[/green] {', '.join(analyst.value for analyst in selected_analysts)}"
    )

    # Step 5: Research depth (skipped when both round counts are set via env).
    # Research depth maps to the debate + risk round counts; when both are
    # supplied through TRADINGAGENTS_MAX_DEBATE_ROUNDS / _MAX_RISK_ROUNDS we keep
    # the run non-interactive and honor the env values (#977).
    depth_from_env = bool(os.environ.get("TRADINGAGENTS_MAX_DEBATE_ROUNDS")) and bool(
        os.environ.get("TRADINGAGENTS_MAX_RISK_ROUNDS")
    )
    if depth_from_env:
        selected_research_depth = DEFAULT_CONFIG["max_debate_rounds"]
        console.print(
            f"[green]✓ Research depth from environment:[/green] "
            f"{DEFAULT_CONFIG['max_debate_rounds']} debate / "
            f"{DEFAULT_CONFIG['max_risk_discuss_rounds']} risk rounds"
        )
    else:
        console.print(
            create_question_box(
                "Step 5: Research Depth", "Select your research depth level"
            )
        )
        selected_research_depth = select_research_depth()

    # Step 6: LLM Provider (skipped when set via TRADINGAGENTS_LLM_PROVIDER).
    # The backend URL comes from TRADINGAGENTS_LLM_BACKEND_URL when set,
    # otherwise the provider's default endpoint — the same value the menu
    # would have picked.
    provider_from_env = bool(os.environ.get("TRADINGAGENTS_LLM_PROVIDER"))
    if provider_from_env:
        selected_llm_provider = DEFAULT_CONFIG["llm_provider"].lower()
        backend_url = resolve_backend_url(
            selected_llm_provider, env_url=DEFAULT_CONFIG["backend_url"]
        )
        console.print(f"[green]✓ LLM provider from environment:[/green] {selected_llm_provider}")
        console.print(f"[green]✓ Backend URL:[/green] {backend_url}")
        # Still confirm/persist the API key so the run doesn't fail later.
        ensure_api_key(selected_llm_provider)
    else:
        console.print(
            create_question_box(
                "Step 6: LLM Provider", "Select your LLM provider"
            )
        )
        selected_llm_provider, backend_url = select_llm_provider()

        # Providers with regional endpoints prompt for the region as a secondary
        # step so the main dropdown stays clean (mainland China and international
        # accounts cannot share API keys).
        if selected_llm_provider == "qwen":
            selected_llm_provider, backend_url = ask_qwen_region()
        elif selected_llm_provider == "minimax":
            selected_llm_provider, backend_url = ask_minimax_region()
        elif selected_llm_provider == "glm":
            selected_llm_provider, backend_url = ask_glm_region()
        elif selected_llm_provider == "opencode":
            selected_llm_provider, backend_url = ask_opencode_endpoint()

        # Honor an explicit env backend URL even when the provider was chosen
        # interactively, so it isn't overwritten by the menu default (#978).
        backend_url = resolve_backend_url(
            selected_llm_provider, backend_url, env_url=DEFAULT_CONFIG["backend_url"]
        )

        # The generic OpenAI-compatible endpoint has no default; ask for it if
        # neither the menu nor the environment supplied one.
        if selected_llm_provider == "openai_compatible" and not backend_url:
            backend_url = prompt_openai_compatible_url()

        # For Ollama, surface the resolved endpoint (OLLAMA_BASE_URL vs default)
        # before model selection so it's obvious where we're connecting.
        if selected_llm_provider == "ollama":
            confirm_ollama_endpoint(backend_url)

        # Confirm the provider's API key is present; prompt the user to paste
        # one and persist it to .env if it's missing, so the analysis run
        # doesn't fail later at the first API call.
        ensure_api_key(selected_llm_provider)

    # Step 7: Thinking agents (skipped when either model is set via environment)
    if os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM") or os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM"):
        selected_shallow_thinker = DEFAULT_CONFIG["quick_think_llm"]
        selected_deep_thinker = DEFAULT_CONFIG["deep_think_llm"]
        console.print(
            f"[green]✓ Thinking agents from environment:[/green] "
            f"quick={selected_shallow_thinker}, deep={selected_deep_thinker}"
        )
    else:
        console.print(
            create_question_box(
                "Step 7: Thinking Agents", "Select your thinking agents for analysis"
            )
        )
        # Loop to allow going back from model selection to provider selection
        while True:
            selected_shallow_thinker = select_shallow_thinking_agent(selected_llm_provider)
            if selected_shallow_thinker == BACK_SENTINEL:
                # Go back to provider selection
                selected_llm_provider, backend_url = select_llm_provider()
                provider_from_env = False
                continue
            selected_deep_thinker = select_deep_thinking_agent(selected_llm_provider)
            if selected_deep_thinker == BACK_SENTINEL:
                # Go back to provider selection
                selected_llm_provider, backend_url = select_llm_provider()
                provider_from_env = False
                continue
            break

    # Step 8: Provider-specific reasoning/thinking configuration. Each knob is
    # settable via its TRADINGAGENTS_* env var; when that var is set (or the
    # provider itself came from env) the prompt is skipped and the configured
    # value is used — same env-precedence rule as the steps above. None = each
    # provider's own default.
    thinking_level = None
    reasoning_effort = None
    anthropic_effort = None
    nvidia_reasoning_effort = None

    provider_lower = selected_llm_provider.lower()
    if provider_from_env:
        thinking_level = DEFAULT_CONFIG["google_thinking_level"]
        reasoning_effort = DEFAULT_CONFIG["openai_reasoning_effort"]
        anthropic_effort = DEFAULT_CONFIG["anthropic_effort"]
        nvidia_reasoning_effort = DEFAULT_CONFIG["nvidia_reasoning_effort"]
    elif provider_lower == "google":
        thinking_level = thinking_value_or_prompt(
            "TRADINGAGENTS_GOOGLE_THINKING_LEVEL", "google_thinking_level",
            "Gemini thinking mode", "Step 8: Thinking Mode",
            "Configure Gemini thinking mode", ask_gemini_thinking_config,
        )
    elif provider_lower == "openai":
        reasoning_effort = thinking_value_or_prompt(
            "TRADINGAGENTS_OPENAI_REASONING_EFFORT", "openai_reasoning_effort",
            "Reasoning effort", "Step 8: Reasoning Effort",
            "Configure OpenAI reasoning effort level", ask_openai_reasoning_effort,
        )
    elif provider_lower == "anthropic":
        anthropic_effort = thinking_value_or_prompt(
            "TRADINGAGENTS_ANTHROPIC_EFFORT", "anthropic_effort",
            "Claude effort", "Step 8: Effort Level",
            "Configure Claude effort level", ask_anthropic_effort,
        )
    elif provider_lower == "nvidia":
        nvidia_reasoning_effort = thinking_value_or_prompt(
            "TRADINGAGENTS_NVIDIA_REASONING_EFFORT", "nvidia_reasoning_effort",
            "Reasoning effort", "Step 8: Reasoning Effort",
            "Configure NVIDIA reasoning effort level", ask_nvidia_reasoning_effort,
        )

    # Step 9: Table-generator model. Used at the end of the run (and from the
    # web Tables tab) to normalize report tables into clean HTML. Env-driven
    # runs reuse the deep thinker so no extra prompt is needed.
    if provider_from_env:
        selected_table_model = selected_deep_thinker
    else:
        console.print(
            create_question_box(
                "Step 9: Tables Model", "Select the model that extracts report tables"
            )
        )
        while True:
            selected_table_model = select_table_model(selected_llm_provider)
            if selected_table_model == BACK_SENTINEL:
                # Go back to provider selection
                selected_llm_provider, backend_url = select_llm_provider()
                provider_from_env = False
                continue
            break

    return {
        "ticker": selected_ticker,
        "asset_type": asset_type.value,
        "analysis_date": analysis_date,
        "analysts": selected_analysts,
        "research_depth": selected_research_depth,
        "llm_provider": selected_llm_provider.lower(),
        "backend_url": backend_url,
        "shallow_thinker": selected_shallow_thinker,
        "deep_thinker": selected_deep_thinker,
        "table_model": selected_table_model,
        "google_thinking_level": thinking_level,
        "openai_reasoning_effort": reasoning_effort,
        "nvidia_reasoning_effort": nvidia_reasoning_effort,
        "anthropic_effort": anthropic_effort,
        "output_language": output_language,
    }


def get_analysis_date(ticker: str | None = None):
    """Get the analysis date from user input with automatic fallback to previous trading day if data missing."""
    from tradingagents.dataflows.stockstats_utils import load_ohlcv
    from tradingagents.dataflows.errors import NoMarketDataError

    def date_has_data(date_str: str) -> bool:
        if not ticker:
            return True
        try:
            df = load_ohlcv(ticker, date_str)
            if df is None or df.empty:
                return False
            # Check if the requested date is actually present in the data
            try:
                requested_ts = pd.to_datetime(date_str).normalize()
                # The DataFrame from load_ohlcv has a 'Date' column (not DatetimeIndex)
                if "Date" in df.columns:
                    date_col = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
                    matches = date_col == requested_ts
                    # Date exists = data available for that trading day (even if close is NaN for today)
                    return matches.any()
                # Fallback: if index is datetime-like
                elif isinstance(df.index, pd.DatetimeIndex):
                    matches = df.index.normalize() == requested_ts
                    return matches.any()
                else:
                    # Last resort: check last row
                    return True
            except Exception:
                return True
        except Exception:
            return False

    while True:
        date_str = typer.prompt(
            "", default=datetime.datetime.now().strftime("%Y-%m-%d")
        )
        try:
            analysis_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            if analysis_date.date() > datetime.datetime.now().date():
                console.print("[red]Error: Analysis date cannot be in the future[/red]")
                continue
            # Validate data availability if ticker known
            if ticker:
                import pandas as pd
                # Try requested date first
                if not date_has_data(date_str):
                    console.print(
                        f"[yellow]No market data for {ticker} on {date_str}. Trying previous trading day...[/yellow]"
                    )
                    # Try up to 10 previous days, skipping weekends
                    for i in range(1, 11):
                        candidate = analysis_date - datetime.timedelta(days=i)
                        # Skip Saturday=5, Sunday=6
                        if candidate.weekday() >= 5:
                            continue
                        fallback = candidate.strftime("%Y-%m-%d")
                        if date_has_data(fallback):
                            console.print(f"[green]Using fallback date {fallback} with available data.[/green]")
                            return fallback
                    console.print(
                        f"[red]No data found for {ticker} in the last 10 days. Please try a different ticker or date.[/red]"
                    )
                    # Ask user to retry
                    retry = typer.prompt("Retry with a different date? [Y/n]", default="Y").strip().upper()
                    if retry in ("Y", "YES", ""):
                        continue
                    else:
                        return date_str
            return date_str
        except ValueError:
            console.print(
                "[red]Error: Invalid date format. Please use YYYY-MM-DD[/red]"
            )


def save_report_to_disk(final_state, ticker: str, save_path: Path):
    """Save the complete analysis report to disk (shared CLI/API writer)."""
    return write_report_tree(final_state, ticker, save_path)


def display_complete_report(final_state):
    """Display the complete analysis report sequentially (avoids truncation)."""
    console.print()
    console.print(Rule("Complete Analysis Report", style="bold green"))

    # I. Analyst Team Reports
    analysts = []
    if final_state.get("market_report"):
        analysts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts.append(("Sentiment Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analysts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analysts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
    if analysts:
        console.print(Panel("[bold]I. Analyst Team Reports[/bold]", border_style="cyan"))
        for title, content in analysts:
            console.print(Panel(Markdown(content), title=title, border_style="blue", padding=(1, 2)))

    # II. Research Team Reports
    if final_state.get("investment_debate_state"):
        debate = final_state["investment_debate_state"]
        research = []
        if debate.get("bull_history"):
            research.append(("Bull Researcher", debate["bull_history"]))
        if debate.get("bear_history"):
            research.append(("Bear Researcher", debate["bear_history"]))
        if debate.get("judge_decision"):
            research.append(("Research Manager", debate["judge_decision"]))
        if research:
            console.print(Panel("[bold]II. Research Team Decision[/bold]", border_style="magenta"))
            for title, content in research:
                console.print(Panel(Markdown(content), title=title, border_style="blue", padding=(1, 2)))

    # III. Trading Team
    if final_state.get("trader_investment_plan"):
        console.print(Panel("[bold]III. Trading Team Plan[/bold]", border_style="yellow"))
        console.print(Panel(Markdown(final_state["trader_investment_plan"]), title="Trader", border_style="blue", padding=(1, 2)))

    # IV. Risk Management Team
    if final_state.get("risk_debate_state"):
        risk = final_state["risk_debate_state"]
        risk_reports = []
        if risk.get("aggressive_history"):
            risk_reports.append(("Aggressive Analyst", risk["aggressive_history"]))
        if risk.get("conservative_history"):
            risk_reports.append(("Conservative Analyst", risk["conservative_history"]))
        if risk.get("neutral_history"):
            risk_reports.append(("Neutral Analyst", risk["neutral_history"]))
        if risk_reports:
            console.print(Panel("[bold]IV. Risk Management Team Decision[/bold]", border_style="red"))
            for title, content in risk_reports:
                console.print(Panel(Markdown(content), title=title, border_style="blue", padding=(1, 2)))

        # V. Portfolio Manager Decision
        if risk.get("judge_decision"):
            console.print(Panel("[bold]V. Portfolio Manager Decision[/bold]", border_style="green"))
            console.print(Panel(Markdown(risk["judge_decision"]), title="Portfolio Manager", border_style="blue", padding=(1, 2)))


def update_research_team_status(status):
    """Update status for research team members (not Trader)."""
    research_team = ["Bull Researcher", "Bear Researcher", "Research Manager"]
    for agent in research_team:
        message_buffer.update_agent_status(agent, status)


# Ordered list of analysts for status transitions
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


def update_analyst_statuses(message_buffer, chunk, wall_time_tracker=None):
    """Update analyst statuses based on accumulated report state.

    Logic:
    - Store new report content from the current chunk if present
    - Check accumulated report_sections (not just current chunk) for status
    - Analysts with reports = completed
    - First analyst without report = in_progress
    - Remaining analysts without reports = pending
    - When all analysts done, set Bull Researcher to in_progress
    """
    selected = message_buffer.selected_analysts
    found_active = False

    if wall_time_tracker is not None:
        sync_analyst_tracker_from_chunk(wall_time_tracker, chunk)

    for analyst_key in ANALYST_ORDER:
        if analyst_key not in selected:
            continue

        agent_name = ANALYST_AGENT_NAMES[analyst_key]
        report_key = ANALYST_REPORT_MAP[analyst_key]

        # Capture new report content from current chunk
        if chunk.get(report_key):
            message_buffer.update_report_section(report_key, chunk[report_key])

        # Determine status from accumulated sections, not just current chunk
        has_report = bool(message_buffer.report_sections.get(report_key))

        if has_report:
            message_buffer.update_agent_status(agent_name, "completed")
        elif not found_active:
            message_buffer.update_agent_status(agent_name, "in_progress")
            found_active = True
        else:
            message_buffer.update_agent_status(agent_name, "pending")

    # When all analysts complete, transition research team to in_progress
    if (
        not found_active
        and selected
        and message_buffer.agent_status.get("Bull Researcher") == "pending"
    ):
        message_buffer.update_agent_status("Bull Researcher", "in_progress")

def extract_content_string(content):
    """Extract string content from various message formats.
    Returns None if no meaningful text content is found.
    """
    import ast

    def is_empty(val):
        """Check if value is empty using Python's truthiness."""
        if val is None or val == '':
            return True
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return True
            try:
                return not bool(ast.literal_eval(s))
            except (ValueError, SyntaxError):
                return False  # Can't parse = real text
        return not bool(val)

    if is_empty(content):
        return None

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, dict):
        text = content.get('text', '')
        return text.strip() if not is_empty(text) else None

    if isinstance(content, list):
        text_parts = [
            item.get('text', '').strip() if isinstance(item, dict) and item.get('type') == 'text'
            else (item.strip() if isinstance(item, str) else '')
            for item in content
        ]
        result = ' '.join(t for t in text_parts if t and not is_empty(t))
        return result if result else None

    return str(content).strip() if not is_empty(content) else None


def classify_message_type(message) -> tuple[str, str | None]:
    """Classify LangChain message into display type and extract content.

    Returns:
        (type, content) - type is one of: User, Agent, Data, Control
                        - content is extracted string or None
    """
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    content = extract_content_string(getattr(message, 'content', None))

    if isinstance(message, HumanMessage):
        if content and content.strip() == "Continue":
            return ("Control", content)
        return ("User", content)

    if isinstance(message, ToolMessage):
        return ("Data", content)

    if isinstance(message, AIMessage):
        return ("Agent", content)

    # Fallback for unknown types
    return ("System", content)


def format_tool_args(args, max_length=80) -> str:
    """Format tool arguments for terminal display."""
    result = str(args)
    if len(result) > max_length:
        return result[:max_length - 3] + "..."
    return result

def _build_run_config(selections: dict, checkpoint: bool | None) -> dict:
    """Assemble the run config from interactive selections, honoring env precedence.

    Round counts and checkpoint follow "explicit env/flag wins": an env-applied
    value on DEFAULT_CONFIG is preserved unless the user overrode it on the CLI.
    """
    config = DEFAULT_CONFIG.copy()
    # Research depth sets both round counts, but an explicit env override
    # (TRADINGAGENTS_MAX_DEBATE_ROUNDS / _MAX_RISK_ROUNDS) wins over the
    # interactive selection — leave the env-applied value in place (#977).
    if not os.environ.get("TRADINGAGENTS_MAX_DEBATE_ROUNDS"):
        config["max_debate_rounds"] = selections["research_depth"]
    if not os.environ.get("TRADINGAGENTS_MAX_RISK_ROUNDS"):
        config["max_risk_discuss_rounds"] = selections["research_depth"]
    config["quick_think_llm"] = selections["shallow_thinker"]
    config["deep_think_llm"] = selections["deep_thinker"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()
    # Provider-specific thinking configuration
    config["google_thinking_level"] = selections.get("google_thinking_level")
    config["openai_reasoning_effort"] = selections.get("openai_reasoning_effort")
    config["anthropic_effort"] = selections.get("anthropic_effort")
    config["nvidia_reasoning_effort"] = selections.get("nvidia_reasoning_effort")
    config["output_language"] = selections.get("output_language", "English")
    # --checkpoint/--no-checkpoint overrides only when explicitly given; omitting
    # the flag preserves TRADINGAGENTS_CHECKPOINT_ENABLED / the default (#976).
    if checkpoint is not None:
        config["checkpoint_enabled"] = checkpoint
    return config


def _normalize_selections(selections: dict) -> dict:
    """Validate + normalize a programmatic selections dict (web/API path).

    Accepts the same keys ``get_user_selections()`` returns; ``analysts``
    may be plain strings. Raises ValueError describing the first problem.
    """
    from cli.models import AnalystType
    from cli.utils import is_valid_ticker_input, normalize_ticker_symbol

    selections = dict(selections)
    ticker = str(selections.get("ticker") or "").strip()
    if not ticker or not is_valid_ticker_input(ticker):
        raise ValueError("ticker must be a valid symbol (e.g. AAPL, 0700.HK, BTC-USD)")
    selections["ticker"] = normalize_ticker_symbol(ticker)

    from cli.utils import detect_asset_type

    selections["asset_type"] = detect_asset_type(selections["ticker"]).value

    import re
    from datetime import datetime as _dt

    date = str(selections.get("analysis_date") or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ValueError("analysis_date must be YYYY-MM-DD")
    try:
        _dt.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise ValueError("analysis_date is not a real calendar date")
    selections["analysis_date"] = date

    analysts = selections.get("analysts") or []
    try:
        selections["analysts"] = [a if isinstance(a, AnalystType) else AnalystType(str(a).lower()) for a in analysts]
    except ValueError:
        raise ValueError("analysts must be among: market, social, news, fundamentals")
    if not selections["analysts"]:
        raise ValueError("select at least one analyst")

    try:
        selections["research_depth"] = int(selections.get("research_depth", 3))
    except (TypeError, ValueError):
        raise ValueError("research_depth must be 1, 3, or 5")
    if selections["research_depth"] not in (1, 3, 5):
        raise ValueError("research_depth must be 1, 3, or 5")

    if not selections.get("llm_provider"):
        raise ValueError("llm_provider is required")
    selections["llm_provider"] = str(selections["llm_provider"]).lower()
    if not selections.get("shallow_thinker") or not selections.get("deep_thinker"):
        raise ValueError("shallow_thinker and deep_thinker are required")
    selections.setdefault("output_language", "English")
    return selections


def run_analysis(checkpoint: bool | None = None, selections: dict | None = None,
                 prompt_hub=None, headless: bool = False, run_record=None):
    """Run one analysis.

    Interactive (CLI) by default: prompts for every selection. Programmatic
    (web/API) when ``selections`` is passed — same keys as
    ``get_user_selections()`` returns, except ``analysts`` may be plain
    strings (e.g. ``["market", "news"]``) instead of ``AnalystType``.
    ``prompt_hub`` (any object with a ``pending_prompt`` dict) receives the
    3 post-run prompts instead of/in addition to the terminal; ``headless``
    silences the fullscreen Live view for server-side runs.
    """
    global dashboard_port
    # Entry choice comes FIRST: full web app or CLI. Web mode boots the
    # servers and exits the CLI; the whole flow then happens in the browser.
    if selections is None and not headless:
        from cli.webapp import ask_entry_mode, launch_full_web

        if ask_entry_mode() == "web":
            url = launch_full_web()
            if url:
                console.print("\n[green]Web stack is running — continuing there. Exiting CLI.[/green]")
            raise typer.Exit()
    # First get all user selections
    if selections is None:
        selections = get_user_selections()
    else:
        selections = _normalize_selections(selections)

    config = _build_run_config(selections, checkpoint)

    # Create stats callback handler for tracking LLM/tool calls
    stats_handler = StatsCallbackHandler()
    if run_record is not None:
        run_record.stats_handler = stats_handler
        run_record.start_time = time.time()

    # Normalize analyst selection to predefined order (selection is a 'set', order is fixed)
    selected_set = {analyst.value for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]
    analyst_execution_plan = build_analyst_execution_plan(selected_analyst_keys)
    analyst_wall_time_tracker = AnalystWallTimeTracker(analyst_execution_plan)

    # Initialize the graph with callbacks bound to LLMs
    graph = TradingAgentsGraph(
        selected_analyst_keys,
        config=config,
        debug=True,
        callbacks=[stats_handler],
    )

    # Initialize message buffer with selected analysts
    message_buffer.init_for_analysis(selected_analyst_keys)

    # Track start time for elapsed display
    start_time = time.time()

    # Create result directory
    results_dir = Path(config["results_dir"]) / selections["ticker"] / selections["analysis_date"]
    results_dir.mkdir(parents=True, exist_ok=True)
    report_dir = results_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_file = results_dir / "message_tool.log"
    log_file.touch(exist_ok=True)

    def save_message_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, message_type, content = obj.messages[-1]
            content = content.replace("\n", " ")  # Replace newlines with spaces
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} [{message_type}] {content}\n")
        return wrapper

    def save_tool_call_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, tool_name, args = obj.tool_calls[-1]
            args_str = ", ".join(f"{k}={v}" for k, v in args.items())
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} [Tool Call] {tool_name}({args_str})\n")
        return wrapper

    def save_report_section_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(section_name, content):
            func(section_name, content)
            if section_name in obj.report_sections and obj.report_sections[section_name] is not None:
                content = obj.report_sections[section_name]
                if content:
                    file_name = f"{section_name}.md"
                    text = "\n".join(str(item) for item in content) if isinstance(content, list) else content
                    with open(report_dir / file_name, "w", encoding="utf-8") as f:
                        f.write(text)
        return wrapper

    message_buffer.add_message = save_message_decorator(message_buffer, "add_message")
    message_buffer.add_tool_call = save_tool_call_decorator(message_buffer, "add_tool_call")
    message_buffer.update_report_section = save_report_section_decorator(message_buffer, "update_report_section")

    # Now start the display layout
    layout = create_layout()

    # Scroll-webpage server always runs (unless TRADINGAGENTS_WEB=0): its URL
    # is shown for 10s, then the TUI takes over. Both stay live for the run.
    # prompt_server feeds the 3 post-run prompts: the interactive dashboard
    # server in CLI mode, or the web run's hub in headless (API) mode.
    prompt_server = prompt_hub
    dashboard_server = None
    if headless:
        dashboard_port = None
    else:

        # Web dashboard: scrollable mirror of the three panels. The Rich Live
        # view takes over the terminal, so print the URL beforehand; it is also
        # repeated in the footer stats line while the run is live.
        dashboard_server, dashboard_url = start_dashboard(
            message_buffer,
            stats_handler=stats_handler,
            start_time=start_time,
            meta={
                "ticker": selections["ticker"],
                "analysis_date": selections["analysis_date"],
                "llm_provider": selections.get("llm_provider"),
                "shallow_thinker": selections.get("shallow_thinker"),
                "deep_thinker": selections.get("deep_thinker"),
            },
        )
        if dashboard_url:
            try:
                dashboard_port = int(dashboard_url.rsplit(":", 1)[-1])
            except ValueError:
                dashboard_port = None
            console.print(f"\n[bold cyan]Web view:[/bold cyan] {dashboard_url}")
            console.print("[dim]Continuing to the terminal view in 10s...[/dim]\n")
            time.sleep(10)
        else:
            dashboard_port = None
        prompt_server = dashboard_server

    # Silent rendering for API-driven runs only: the Live view renders into
    # a discarded console so server logs stay clean.
    # UTF-8: the locale default (cp1252 on Windows) cannot encode the ⏱/arrow
    # symbols in the panels and would raise inside the render itself.
    _devnull = open(os.devnull, "w", encoding="utf-8") if headless else None
    live_kwargs = (
        {"refresh_per_second": 2, "screen": False, "redirect_stderr": False,
         "console": Console(file=_devnull)}
        if headless
        else {"refresh_per_second": 30, "screen": True, "redirect_stderr": False}
    )
    with Live(layout, **live_kwargs):
        # Initial display
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # Add keyboard listener for scrolling
        try:
            from pynput import keyboard
            
            def on_key_press(key):
                try:
                    if key == keyboard.Key.up:
                        scroll_state.messages_offset = max(0, scroll_state.messages_offset - 1)
                        update_display(layout, stats_handler=stats_handler, start_time=start_time)
                    elif key == keyboard.Key.down:
                        scroll_state.messages_offset += 1
                        update_display(layout, stats_handler=stats_handler, start_time=start_time)
                    elif key == keyboard.Key.page_up:
                        scroll_state.analysis_offset = max(0, scroll_state.analysis_offset - 10)
                        update_display(layout, stats_handler=stats_handler, start_time=start_time)
                    elif key == keyboard.Key.page_down:
                        scroll_state.analysis_offset += 10
                        update_display(layout, stats_handler=stats_handler, start_time=start_time)
                    elif key == keyboard.Key.left:
                        scroll_state.progress_offset = max(0, scroll_state.progress_offset - 1)
                        update_display(layout, stats_handler=stats_handler, start_time=start_time)
                    elif key == keyboard.Key.right:
                        scroll_state.progress_offset += 1
                        update_display(layout, stats_handler=stats_handler, start_time=start_time)
                except Exception:
                    pass  # Ignore errors in key handling
            
            # Start keyboard listener in a separate thread
            listener = keyboard.Listener(on_press=on_key_press)
            listener.start()
        except ImportError:
            # If pynput is not available, keyboard scrolling won't work
            pass

        # Add initial messages
        message_buffer.add_message("System", f"Selected ticker: {selections['ticker']}")
        if selections["asset_type"] != "stock":
            message_buffer.add_message("System", f"Detected asset type: {selections['asset_type']}")
        message_buffer.add_message(
            "System", f"Analysis date: {selections['analysis_date']}"
        )
        message_buffer.add_message(
            "System",
            f"Selected analysts: {', '.join(analyst.value for analyst in selections['analysts'])}",
        )
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # Update agent status to in_progress for the first analyst
        first_analyst = get_initial_analyst_node(analyst_execution_plan)
        message_buffer.update_agent_status(first_analyst, "in_progress")
        analyst_wall_time_tracker.mark_started(selected_analyst_keys[0])
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # Create spinner text
        spinner_text = (
            f"Analyzing {selections['ticker']} on {selections['analysis_date']}..."
        )
        update_display(layout, spinner_text, stats_handler=stats_handler, start_time=start_time)

        # Initialize state and get graph args with callbacks.
        # Resolve the instrument identity once here so all agents anchor to
        # the real company (#814); the CLI builds state directly rather than
        # going through propagate(), so this must happen on the CLI path too.
        instrument_context = graph.resolve_instrument_context(
            selections["ticker"], selections["asset_type"]
        )
        init_agent_state = graph.propagator.create_initial_state(
            selections["ticker"],
            selections["analysis_date"],
            asset_type=selections["asset_type"],
            instrument_context=instrument_context,
        )
        # Pass callbacks to graph config for tool execution tracking
        # (LLM tracking is handled separately via LLM constructor)
        args = graph.propagator.get_graph_args(callbacks=[stats_handler])

        # Recompile with a checkpointer and inject the thread_id so --checkpoint
        # actually saves and resumes on the CLI path (#1249); a no-op when
        # checkpointing is disabled. Torn down in the finally below.
        checkpoint_tid = graph.begin_checkpoint(
            selections["ticker"], selections["analysis_date"], selections["asset_type"]
        )
        if checkpoint_tid is not None:
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = checkpoint_tid

        # Stream the analysis. On resume, feed None so LangGraph continues the
        # interrupted run instead of re-appending the initial state (#1249); the
        # try/finally tears the checkpointer down even if the stream raises.
        trace = []
        try:
            for chunk in graph.graph.stream(graph.checkpoint_input(init_agent_state), **args):
                # Process all messages in chunk, deduplicating by message ID
                for message in chunk.get("messages", []):
                    msg_id = getattr(message, "id", None)
                    if msg_id is not None:
                        if msg_id in message_buffer._processed_message_ids:
                            continue
                        message_buffer._processed_message_ids.add(msg_id)

                    msg_type, content = classify_message_type(message)
                    if content and content.strip():
                        message_buffer.add_message(msg_type, content)

                    if hasattr(message, "tool_calls") and message.tool_calls:
                        for tool_call in message.tool_calls:
                            if isinstance(tool_call, dict):
                                message_buffer.add_tool_call(tool_call["name"], tool_call["args"])
                            else:
                                message_buffer.add_tool_call(tool_call.name, tool_call.args)

                # Update analyst statuses based on report state (runs on every chunk)
                update_analyst_statuses(
                    message_buffer,
                    chunk,
                    wall_time_tracker=analyst_wall_time_tracker,
                )

                # Research Team - Handle Investment Debate State
                if chunk.get("investment_debate_state"):
                    debate_state = chunk["investment_debate_state"]
                    bull_hist = debate_state.get("bull_history", "").strip()
                    bear_hist = debate_state.get("bear_history", "").strip()
                    judge = debate_state.get("judge_decision", "").strip()

                    # Only update status when there's actual content
                    if bull_hist or bear_hist:
                        update_research_team_status("in_progress")
                    if bull_hist:
                        message_buffer.update_report_section(
                            "investment_plan", f"### Bull Researcher Analysis\n{bull_hist}"
                        )
                    if bear_hist:
                        message_buffer.update_report_section(
                            "investment_plan", f"### Bear Researcher Analysis\n{bear_hist}"
                        )
                    if judge:
                        message_buffer.update_report_section(
                            "investment_plan", f"### Research Manager Decision\n{judge}"
                        )
                        update_research_team_status("completed")
                        message_buffer.update_agent_status("Trader", "in_progress")

                # Trading Team
                if chunk.get("trader_investment_plan"):
                    message_buffer.update_report_section(
                        "trader_investment_plan", chunk["trader_investment_plan"]
                    )
                    if message_buffer.agent_status.get("Trader") != "completed":
                        message_buffer.update_agent_status("Trader", "completed")
                        message_buffer.update_agent_status("Aggressive Analyst", "in_progress")

                # Risk Management Team - Handle Risk Debate State
                if chunk.get("risk_debate_state"):
                    risk_state = chunk["risk_debate_state"]
                    agg_hist = risk_state.get("aggressive_history", "").strip()
                    con_hist = risk_state.get("conservative_history", "").strip()
                    neu_hist = risk_state.get("neutral_history", "").strip()
                    judge = risk_state.get("judge_decision", "").strip()

                    if agg_hist:
                        if message_buffer.agent_status.get("Aggressive Analyst") != "completed":
                            message_buffer.update_agent_status("Aggressive Analyst", "in_progress")
                        message_buffer.update_report_section(
                            "final_trade_decision", f"### Aggressive Analyst Analysis\n{agg_hist}"
                        )
                    if con_hist:
                        if message_buffer.agent_status.get("Conservative Analyst") != "completed":
                            message_buffer.update_agent_status("Conservative Analyst", "in_progress")
                        message_buffer.update_report_section(
                            "final_trade_decision", f"### Conservative Analyst Analysis\n{con_hist}"
                        )
                    if neu_hist:
                        if message_buffer.agent_status.get("Neutral Analyst") != "completed":
                            message_buffer.update_agent_status("Neutral Analyst", "in_progress")
                        message_buffer.update_report_section(
                            "final_trade_decision", f"### Neutral Analyst Analysis\n{neu_hist}"
                        )
                    if judge and message_buffer.agent_status.get("Portfolio Manager") != "completed":
                        message_buffer.update_agent_status("Portfolio Manager", "in_progress")
                        message_buffer.update_report_section(
                            "final_trade_decision", f"### Portfolio Manager Decision\n{judge}"
                        )
                        message_buffer.update_agent_status("Aggressive Analyst", "completed")
                        message_buffer.update_agent_status("Conservative Analyst", "completed")
                        message_buffer.update_agent_status("Neutral Analyst", "completed")
                        message_buffer.update_agent_status("Portfolio Manager", "completed")

                # Update the display
                update_display(layout, stats_handler=stats_handler, start_time=start_time)

                trace.append(chunk)

            # Clean run: drop this run's checkpoint so a later run starts fresh.
            # A mid-stream failure skips this, keeping the checkpoint for resume.
            graph.clear_checkpoint_on_success(
                selections["ticker"], selections["analysis_date"], selections["asset_type"]
            )
        finally:
            # Always restore the plain uncheckpointed graph, even on failure.
            graph.end_checkpoint()

        # Streamed chunks are per-node deltas, not full state. Merge them
        # so every report field populated across the run is present.
        final_state = {}
        for chunk in trace:
            final_state.update(chunk)

        # Update all agent statuses to completed
        for agent in message_buffer.agent_status:
            message_buffer.update_agent_status(agent, "completed")

        message_buffer.add_message(
            "System", f"Completed analysis for {selections['analysis_date']}"
        )
        message_buffer.add_message("System", analyst_wall_time_tracker.format_summary())

        # Update final report sections
        for section in message_buffer.report_sections:
            if section in final_state:
                message_buffer.update_report_section(section, final_state[section])

        update_display(layout, stats_handler=stats_handler, start_time=start_time)

    # Post-analysis prompts (outside Live context for clean interaction).
    # The dashboard stays up through these so they can be answered from the
    # prompt bar on the page or in the terminal, whichever comes first.
    console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")
    console.print(f"[dim]{analyst_wall_time_tracker.format_summary()}[/dim]")

    # Prompt to save report
    save_choice = ask_everywhere(prompt_server, "Save report?", default="Y").strip().upper()
    saved_dir = None
    if save_choice in ("Y", "YES", ""):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = Path.cwd() / "reports" / f"{selections['ticker']}_{timestamp}"
        save_path_str = (
            ask_everywhere(
                prompt_server,
                "Save path (press Enter for default)",
                default=str(default_path),
            ).strip()
            or str(default_path)
        )
        save_path = Path(save_path_str)
        try:
            report_file = save_report_to_disk(final_state, selections["ticker"], save_path)
            saved_dir = save_path
            console.print(f"\n[green]✓ Report saved to:[/green] {save_path.resolve()}")
            console.print(f"  [dim]Complete report:[/dim] {report_file.name}")
        except Exception as e:
            console.print(f"[red]Error saving report: {e}[/red]")

    # Prompt to display full report
    display_choice = ask_everywhere(
        prompt_server, "Display full report on screen?", default="Y"
    ).strip().upper()
    if display_choice in ("Y", "YES", ""):
        display_complete_report(final_state)

    # Prompt to generate structured tables from the report sections.
    tables_choice = ask_everywhere(
        prompt_server, "Generate tables from the report?", default="Y"
    ).strip().upper()
    if tables_choice in ("Y", "YES", ""):
        from tradingagents.reporting_tables import generate_tables_for_session

        table_target = saved_dir if saved_dir is not None else results_dir
        table_kind = "saved" if saved_dir is not None else "run"
        table_model = selections.get("table_model") or selections.get("deep_thinker")
        console.print(
            f"\n[bold cyan]Extracting tables with {table_model}...[/bold cyan]"
        )
        try:
            def _table_progress(agent_label, count):
                console.print(f"  [dim]{agent_label}: {count} table(s)[/dim]")

            tables = generate_tables_for_session(
                table_target,
                table_kind,
                selections["llm_provider"],
                table_model,
                selections.get("backend_url"),
                progress_cb=_table_progress,
            )
            total = sum(len(v) for v in tables.values())
            console.print(f"[green]✓ Tables saved ({total} across {len(tables)} sections)[/green]")
        except Exception as e:
            console.print(f"[red]Table generation failed: {e}[/red]")

    stop_dashboard(dashboard_server)
    dashboard_port = None

    if run_record is not None:
        run_record.final_state = final_state
        run_record.status = "done"


@app.callback(invoke_without_command=True)
def _default(
    ctx: typer.Context,
    checkpoint: bool | None = typer.Option(
        None,
        "--checkpoint/--no-checkpoint",
        help="Enable/disable checkpoint-resume (save state after each node so a "
        "crashed run can resume). Omit to honor TRADINGAGENTS_CHECKPOINT_ENABLED.",
    ),
    clear_checkpoints: bool = typer.Option(
        False,
        "--clear-checkpoints",
        help="Delete all saved checkpoints before running (force fresh start).",
    ),
):
    """TradingAgents CLI (default: run analysis)."""
    if ctx.invoked_subcommand is None:
        analyze(checkpoint=checkpoint, clear_checkpoints=clear_checkpoints)


@app.command()
def analyze(
    checkpoint: bool | None = typer.Option(
        None,
        "--checkpoint/--no-checkpoint",
        help="Enable/disable checkpoint-resume (save state after each node so a "
        "crashed run can resume). Omit to honor TRADINGAGENTS_CHECKPOINT_ENABLED.",
    ),
    clear_checkpoints: bool = typer.Option(
        False,
        "--clear-checkpoints",
        help="Delete all saved checkpoints before running (force fresh start).",
    ),
):
    if clear_checkpoints:
        from tradingagents.graph.checkpointer import clear_all_checkpoints
        n = clear_all_checkpoints(DEFAULT_CONFIG["data_cache_dir"])
        console.print(f"[yellow]Cleared {n} checkpoint(s).[/yellow]")
    while True:
        try:
            run_analysis(checkpoint=checkpoint)
            console.print("\n[dim]Restarting TradingAgents CLI...[/dim]")
        except _NO_CONSOLE_ERRORS:
            # A terminal with no console buffer cannot host the interactive prompts.
            # Emit one actionable line on stderr instead of a prompt_toolkit
            # traceback; plain text, since rich may not render here either (#1138).
            typer.echo(
                "Error: no Windows console available. The interactive CLI needs a real "
                "console buffer — run it from Windows Terminal, PowerShell, or cmd.exe "
                "rather than a piped or embedded terminal.",
                err=True,
            )
            raise typer.Exit(code=1) from None
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user. Exiting TradingAgents CLI.[/yellow]")
            break


@app.command()
def web(
    port: int = typer.Option(
        8787,
        "--port",
        help="Port for the web API (the Next.js app's backend). "
        "Omit to honor TRADINGAGENTS_API_PORT.",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Interface to bind the web API to.",
    ),
):
    """Start the TradingAgents web API (backend for the Next.js app)."""
    from cli.api_server import serve_forever

    serve_forever(host, port)


if __name__ == "__main__":
    app()
