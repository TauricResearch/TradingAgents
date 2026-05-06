import datetime
from html import escape
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, cast
import textwrap

import typer
from dotenv import load_dotenv
from markdown_it import MarkdownIt
from rich import box
from rich.align import Align
from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.text import Text
from rich.table import Table

from cli.announcements import fetch_announcements, display_announcements
from cli.llm_config import LLMConfigOverrides, ResolvedLLMConfig, resolve_llm_config
from cli.models import AnalystType
from cli.stats_handler import StatsCallbackHandler
from cli.utils import (
    ask_anthropic_effort,
    ask_gemini_thinking_config,
    ask_openai_reasoning_effort,
    ask_output_language,
    normalize_ticker_symbol,
    select_analysts,
    select_deep_thinking_agent,
    select_llm_provider,
    select_research_depth,
    select_shallow_thinking_agent,
)
from tradingagents.batch import (
    load_batch_inputs,
    run_batch_analysis,
)
from tradingagents.allocation import AllocationPolicy
from tradingagents.charts import ChartArtifact, generate_report_charts
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.execution import DryRunExecutor, ExecutionAction, ExecutionOrder
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Load environment variables
load_dotenv()
load_dotenv(".env.enterprise", override=False)

console = Console()

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents CLI: Multi-Agents LLM Financial Trading Framework",
    add_completion=True,  # Enable shell completion
)


@dataclass(frozen=True)
class SelectionOverrides:
    ticker: str | None = None
    analysis_date: str | None = None
    output_language: str | None = None
    analysts: list[AnalystType] | None = None
    research_depth: int | None = None
    save_report: bool | None = None
    save_path: Path | None = None
    display_report: bool | None = None


@dataclass(frozen=True)
class AnalysisRunResult:
    ticker: str
    final_state: dict[str, Any]
    report_path: Path | None = None
    save_path: Path | None = None


def _execution_orders_from_allocation_plan(allocation_plan: Any) -> list[ExecutionOrder]:
    orders: list[ExecutionOrder] = []
    for row in allocation_plan.rows:
        if row.quantity_delta is None or row.quantity_delta == 0:
            continue
        action: ExecutionAction = "buy" if row.quantity_delta > 0 else "sell"
        orders.append(
            ExecutionOrder(
                ticker=row.ticker,
                action=action,
                quantity=abs(row.quantity_delta),
            )
        )
    return orders


def _print_execution_dry_run_table(console: Any, allocation_plan: Any) -> None:
    executor = DryRunExecutor()
    results_by_ticker = {
        result.order.ticker: result
        for result in executor.execute(_execution_orders_from_allocation_plan(allocation_plan))
    }

    table = Table(title="Allocation Dry Run")
    table.add_column("Ticker")
    table.add_column("Action")
    table.add_column("Quantity Delta", justify="right")
    table.add_column("Leftover Cash", justify="right")

    for row in allocation_plan.rows:
        quantity = (
            ""
            if row.quantity_delta is None
            else _format_execution_quantity(row.quantity_delta)
        )
        result = results_by_ticker.get(row.ticker)
        table.add_row(
            row.ticker,
            result.order.action if result is not None else row.recommended_action,
            quantity,
            _format_execution_number(allocation_plan.leftover_cash),
        )
    console.print(table)


def _format_execution_number(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _format_execution_quantity(value: float | None) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4f}"


def _install_cli_dry_run_executor() -> None:
    import tradingagents.batch as batch_module

    batch_module._print_dry_run_table = _print_execution_dry_run_table


_install_cli_dry_run_executor()


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
        "social": "Social Analyst",
        "news": "News Analyst",
        "fundamentals": "Fundamentals Analyst",
    }

    # Report section mapping: section -> (analyst_key for filtering, finalizing_agent)
    # analyst_key: which analyst selection controls this section (None = always included)
    # finalizing_agent: which agent must be "completed" for this report to count as done
    REPORT_SECTIONS = {
        "market_report": ("market", "Market Analyst"),
        "sentiment_report": ("social", "Social Analyst"),
        "news_report": ("news", "News Analyst"),
        "fundamentals_report": ("fundamentals", "Fundamentals Analyst"),
        "investment_plan": (None, "Research Manager"),
        "trader_investment_plan": (None, "Trader"),
        "final_trade_decision": (None, "Portfolio Manager"),
    }

    def __init__(self, max_length=100, logger: "RunLogger | None" = None):
        self.messages: deque[Any] = deque(maxlen=max_length)
        self.tool_calls: deque[Any] = deque(maxlen=max_length)
        self.logger = logger
        self.current_report = None
        self.final_report = None  # Store the complete final report
        self.agent_status: dict[str, str] = {}
        self.current_agent = None
        self.report_sections: dict[str, str] = {}
        self.selected_analysts: list[str] = []
        self._processed_message_ids: set[str] = set()

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

    def add_message(self, message_type, content):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.messages.append((timestamp, message_type, content))
        if self.logger:
            self.logger.log_message(timestamp, message_type, content)

    def add_tool_call(self, tool_name, args):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.tool_calls.append((timestamp, tool_name, args))
        if self.logger:
            self.logger.log_tool_call(timestamp, tool_name, args)

    def update_agent_status(self, agent, status):
        if agent in self.agent_status:
            self.agent_status[agent] = status
            self.current_agent = agent

    def update_report_section(self, section_name, content):
        if section_name in self.report_sections:
            self.report_sections[section_name] = content
            self._update_current_report()
            if self.logger and self.report_sections[section_name] is not None:
                self.logger.write_report_section(
                    section_name, self.report_sections[section_name]
                )

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


class RunLogger:
    def __init__(self, log_file: Path, report_dir: Path):
        self.log_file = log_file
        self.report_dir = report_dir

    def log_message(self, timestamp: str, message_type: str, content: str) -> None:
        text = str(content).replace("\n", " ")
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} [{message_type}] {text}\n")

    def log_tool_call(self, timestamp: str, tool_name: str, args: dict) -> None:
        args_str = ", ".join(f"{k}={v}" for k, v in args.items())
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} [Tool Call] {tool_name}({args_str})\n")

    def write_report_section(self, section_name: str, content: str | list) -> None:
        text = "\n".join(str(item) for item in content) if isinstance(content, list) else content
        with open(self.report_dir / f"{section_name}.md", "w", encoding="utf-8") as f:
            f.write(text)


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


def update_display(layout, message_buffer: MessageBuffer, spinner_text=None, stats_handler=None, start_time=None):
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
            "Social Analyst",
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

    for team, agents in teams.items():
        # Add first agent with team name
        first_agent = agents[0]
        status = message_buffer.agent_status.get(first_agent, "pending")
        status_cell: RenderableType
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
        if len(content_str) > 200:
            content_str = content_str[:197] + "..."
        all_messages.append((timestamp, msg_type, content_str))

    # Sort by timestamp descending (newest first)
    all_messages.sort(key=lambda x: x[0], reverse=True)

    # Calculate how many messages we can show based on available space
    max_messages = 12

    # Get the first N messages (newest ones)
    recent_messages = all_messages[:max_messages]

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
        layout["analysis"].update(
            Panel(
                Markdown(message_buffer.current_report),
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

    # Elapsed time
    if start_time:
        elapsed = time.time() - start_time
        elapsed_str = f"\u23f1 {int(elapsed // 60):02d}:{int(elapsed % 60):02d}"
        stats_parts.append(elapsed_str)

    stats_table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
    stats_table.add_column("Stats", justify="center")
    stats_table.add_row(" | ".join(stats_parts))

    layout["footer"].update(Panel(stats_table, border_style="grey50"))


def get_user_selections(
    resolved_llm: ResolvedLLMConfig | None = None,
    selection_overrides: SelectionOverrides | None = None,
):
    """Get all user selections before starting the analysis display."""
    selection_overrides = selection_overrides or SelectionOverrides()
    selected_ticker = selection_overrides.ticker
    analysis_date = selection_overrides.analysis_date
    output_language = selection_overrides.output_language
    selected_analysts = selection_overrides.analysts
    selected_research_depth = selection_overrides.research_depth

    has_all_run_inputs = bool(
        selected_ticker
        and analysis_date
        and output_language
        and selected_analysts
        and selected_research_depth is not None
        and resolved_llm
        and resolved_llm.is_complete
    )

    if has_all_run_inputs:
        assert resolved_llm is not None
        assert selected_ticker is not None
        assert analysis_date is not None
        assert output_language is not None
        assert selected_analysts is not None
        assert selected_research_depth is not None
        return _build_user_selections(
            resolved_llm=resolved_llm,
            selected_ticker=selected_ticker,
            analysis_date=analysis_date,
            output_language=output_language,
            selected_analysts=selected_analysts,
            selected_research_depth=selected_research_depth,
        )

    # Display ASCII art welcome message
    with open(Path(__file__).parent / "static" / "welcome.txt", "r", encoding="utf-8") as f:
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

    if not selected_ticker:
        # Step 1: Ticker symbol
        console.print(
            create_question_box(
                "Step 1: Ticker Symbol",
                "Enter the exact ticker symbol to analyze, including exchange suffix when needed (examples: SPY, CNC.TO, 7203.T, 0700.HK)",
                "SPY",
            )
        )
        selected_ticker = get_ticker()

    if not analysis_date:
        # Step 2: Analysis date
        default_date = datetime.datetime.now().strftime("%Y-%m-%d")
        console.print(
            create_question_box(
                "Step 2: Analysis Date",
                "Enter the analysis date (YYYY-MM-DD)",
                default_date,
            )
        )
        analysis_date = get_analysis_date()

    if not output_language:
        # Step 3: Output language
        console.print(
            create_question_box(
                "Step 3: Output Language",
                "Select the language for analyst reports and final decision"
            )
        )
        output_language = ask_output_language()

    if not selected_analysts:
        # Step 4: Select analysts
        console.print(
            create_question_box(
                "Step 4: Analysts Team", "Select your LLM analyst agents for the analysis"
            )
        )
        selected_analysts = select_analysts()
        console.print(
            f"[green]Selected analysts:[/green] {', '.join(analyst.value for analyst in selected_analysts)}"
        )

    if selected_research_depth is None:
        # Step 5: Research depth
        console.print(
            create_question_box(
                "Step 5: Research Depth", "Select your research depth level"
            )
        )
        selected_research_depth = select_research_depth()

    selected_llm_provider = resolved_llm.provider if resolved_llm else None
    backend_url = resolved_llm.backend_url if resolved_llm else None

    # Step 6: LLM Provider
    if not selected_llm_provider:
        console.print(
            create_question_box(
                "Step 6: LLM Provider", "Select your LLM provider"
            )
        )
        selected_llm_provider, selected_backend_url = select_llm_provider()
        if backend_url is None:
            backend_url = selected_backend_url

    # Step 7: Thinking agents
    selected_shallow_thinker = resolved_llm.quick_model if resolved_llm else None
    selected_deep_thinker = resolved_llm.deep_model if resolved_llm else None
    if not selected_shallow_thinker or not selected_deep_thinker:
        console.print(
            create_question_box(
                "Step 7: Thinking Agents", "Select your thinking agents for analysis"
            )
        )
    if not selected_shallow_thinker:
        selected_shallow_thinker = select_shallow_thinking_agent(selected_llm_provider)
    if not selected_deep_thinker:
        selected_deep_thinker = select_deep_thinking_agent(selected_llm_provider)

    # Step 8: Provider-specific thinking configuration
    thinking_level = resolved_llm.google_thinking_level if resolved_llm else None
    reasoning_effort = resolved_llm.openai_reasoning_effort if resolved_llm else None
    anthropic_effort = resolved_llm.anthropic_effort if resolved_llm else None

    provider_lower = selected_llm_provider.lower()
    if provider_lower == "google" and not thinking_level:
        console.print(
            create_question_box(
                "Step 8: Thinking Mode",
                "Configure Gemini thinking mode"
            )
        )
        thinking_level = ask_gemini_thinking_config()
    elif provider_lower == "openai" and not backend_url and not reasoning_effort:
        console.print(
            create_question_box(
                "Step 8: Reasoning Effort",
                "Configure OpenAI reasoning effort level"
            )
        )
        reasoning_effort = ask_openai_reasoning_effort()
    elif provider_lower == "anthropic" and not anthropic_effort:
        console.print(
            create_question_box(
                "Step 8: Effort Level",
                "Configure Claude effort level"
            )
        )
        anthropic_effort = ask_anthropic_effort()

    return _build_user_selections(
        resolved_llm=ResolvedLLMConfig(
            provider=selected_llm_provider,
            quick_model=selected_shallow_thinker,
            deep_model=selected_deep_thinker,
            backend_url=backend_url,
            google_thinking_level=thinking_level,
            openai_reasoning_effort=reasoning_effort,
            anthropic_effort=anthropic_effort,
        ),
        selected_ticker=selected_ticker,
        analysis_date=analysis_date,
        output_language=output_language,
        selected_analysts=selected_analysts,
        selected_research_depth=selected_research_depth,
    )


def _build_user_selections(
    *,
    resolved_llm: ResolvedLLMConfig,
    selected_ticker: str,
    analysis_date: str,
    output_language: str,
    selected_analysts: list[AnalystType],
    selected_research_depth: int,
) -> dict[str, Any]:
    return {
        "ticker": selected_ticker,
        "analysis_date": analysis_date,
        "analysts": selected_analysts,
        "research_depth": selected_research_depth,
        "llm_provider": cast(str, resolved_llm.provider).lower(),
        "backend_url": resolved_llm.backend_url,
        "shallow_thinker": resolved_llm.quick_model,
        "deep_thinker": resolved_llm.deep_model,
        "google_thinking_level": resolved_llm.google_thinking_level,
        "openai_reasoning_effort": resolved_llm.openai_reasoning_effort,
        "anthropic_effort": resolved_llm.anthropic_effort,
        "output_language": output_language,
    }


def get_ticker():
    """Get ticker symbol from user input."""
    return typer.prompt("", default="SPY")


def get_analysis_date():
    """Get the analysis date from user input."""
    while True:
        date_str = typer.prompt(
            "", default=datetime.datetime.now().strftime("%Y-%m-%d")
        )
        try:
            # Validate date format and ensure it's not in the future
            analysis_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            if analysis_date.date() > datetime.datetime.now().date():
                console.print("[red]Error: Analysis date cannot be in the future[/red]")
                continue
            return date_str
        except ValueError:
            console.print(
                "[red]Error: Invalid date format. Please use YYYY-MM-DD[/red]"
            )


def render_markdown_report_html(markdown_text: str, title: str) -> str:
    """Render report Markdown as a standalone HTML document."""
    body = MarkdownIt("commonmark", {"html": False}).enable("table").render(markdown_text)
    safe_title = escape(title, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --text: #1f2933;
      --muted: #52616f;
      --border: #d9e2ec;
      --surface: #ffffff;
      --accent: #0b7285;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.6;
    }}
    main {{
      max-width: 1040px;
      margin: 0 auto;
      padding: 40px 24px 64px;
      background: var(--surface);
      min-height: 100vh;
    }}
    h1, h2, h3, h4 {{
      line-height: 1.25;
      color: #102a43;
    }}
    h1 {{
      margin-top: 0;
      padding-bottom: 16px;
      border-bottom: 2px solid var(--accent);
    }}
    h2 {{
      margin-top: 40px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }}
    h3 {{
      margin-top: 28px;
    }}
    p, li {{
      color: var(--text);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 20px 0;
      font-size: 0.95rem;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 8px 10px;
      vertical-align: top;
    }}
    th {{
      background: #edf2f7;
      text-align: left;
    }}
    code {{
      background: #edf2f7;
      border-radius: 4px;
      padding: 2px 4px;
      font-family: "SFMono-Regular", Consolas, monospace;
    }}
    pre {{
      overflow-x: auto;
      background: #102a43;
      color: #f0f4f8;
      padding: 16px;
      border-radius: 6px;
    }}
    blockquote {{
      margin-left: 0;
      padding-left: 16px;
      border-left: 4px solid var(--accent);
      color: var(--muted);
    }}
    img {{
      max-width: 100%;
      height: auto;
      display: block;
    }}
    @media (max-width: 720px) {{
      main {{
        padding: 24px 16px 48px;
      }}
      table {{
        display: block;
        overflow-x: auto;
      }}
    }}
  </style>
</head>
<body>
  <main>
{body}
  </main>
</body>
</html>
"""


def build_llm_report_metadata(selections: dict[str, Any]) -> dict[str, str]:
    """Build stable LLM metadata for UI and saved reports."""
    metadata = {
        "LLM Provider": str(selections["llm_provider"]),
        "Quick Model": str(selections["shallow_thinker"]),
        "Deep Model": str(selections["deep_thinker"]),
    }
    if selections.get("backend_url"):
        metadata["Backend URL"] = str(selections["backend_url"])
    return metadata


def format_llm_runtime_summary(metadata: dict[str, str]) -> str:
    quick = metadata["Quick Model"]
    deep = metadata["Deep Model"]
    provider = metadata["LLM Provider"]
    return f"LLM: {provider} | quick: {quick} | deep: {deep}"


def format_report_metadata(metadata: dict[str, str] | None) -> str:
    if not metadata:
        return ""
    return "\n".join(f"**{key}**: {value}" for key, value in metadata.items()) + "\n\n"


def format_chart_section(artifacts: list[ChartArtifact], save_path: Path) -> str:
    lines = ["## Technical Charts"]
    for artifact in artifacts:
        relative_path = artifact.path.relative_to(save_path).as_posix()
        lines.append("")
        lines.append(f"[![{artifact.title}]({relative_path})]({relative_path})")
        lines.append("")
        lines.append(artifact.description)
    return "\n".join(lines)


def write_pdf_report(
    markdown_text: str,
    pdf_path: Path,
    *,
    title: str,
    report_metadata: dict[str, str] | None = None,
    chart_artifacts: list[ChartArtifact] | None = None,
) -> Path:
    """Write a lightweight PDF report with text, metadata, and chart pages."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    chart_artifacts = chart_artifacts or []

    with PdfPages(pdf_path) as pdf:
        info = pdf.infodict()
        info["Title"] = title
        info["Subject"] = "TradingAgents analysis report"
        info["Creator"] = "TradingAgents"
        if report_metadata:
            info["Keywords"] = "; ".join(f"{key}: {value}" for key, value in report_metadata.items())

        for page in _pdf_text_pages(markdown_text, title):
            fig = plt.figure(figsize=(8.5, 11))
            fig.patch.set_facecolor("white")
            fig.text(0.07, 0.95, page["header"], fontsize=14, fontweight="bold", va="top")
            fig.text(
                0.07,
                0.90,
                page["body"],
                fontsize=9,
                family="monospace",
                va="top",
                linespacing=1.25,
            )
            fig.text(0.5, 0.03, f"Page {page['number']}", fontsize=8, ha="center", color="#666666")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        for artifact in chart_artifacts:
            if not artifact.path.exists():
                continue
            try:
                image = mpimg.imread(artifact.path)
            except Exception:
                continue
            fig, ax = plt.subplots(figsize=(11, 8.5))
            fig.patch.set_facecolor("white")
            ax.imshow(image)
            ax.axis("off")
            fig.suptitle(artifact.title, fontsize=14, fontweight="bold")
            fig.text(0.5, 0.04, artifact.description, ha="center", va="bottom", fontsize=9, wrap=True)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

    return pdf_path


class PdfTextPage(TypedDict):
    number: int
    header: str
    body: str


def _pdf_text_pages(markdown_text: str, title: str) -> list[PdfTextPage]:
    wrapped_lines: list[str] = []
    for raw_line in markdown_text.splitlines():
        if not raw_line:
            wrapped_lines.append("")
            continue
        wrapped = textwrap.wrap(raw_line, width=96, replace_whitespace=False) or [raw_line]
        wrapped_lines.extend(wrapped)

    lines_per_page = 58
    pages: list[PdfTextPage] = []
    for start in range(0, len(wrapped_lines), lines_per_page):
        body = "\n".join(wrapped_lines[start:start + lines_per_page])
        pages.append({
            "number": len(pages) + 1,
            "header": title,
            "body": body,
        })
    if not pages:
        pages.append({"number": 1, "header": title, "body": ""})
    return pages


def save_report_to_disk(
    final_state,
    ticker: str,
    save_path: Path,
    report_metadata: dict[str, str] | None = None,
):
    """Save complete analysis report to disk with organized subfolders."""
    save_path.mkdir(parents=True, exist_ok=True)
    sections = []
    chart_artifacts: list[ChartArtifact] = []

    symbol = final_state.get("company_of_interest") or ticker
    trade_date = final_state.get("trade_date")
    if symbol and trade_date:
        try:
            chart_artifacts = generate_report_charts(str(symbol), str(trade_date), save_path)
            if chart_artifacts:
                sections.append(format_chart_section(chart_artifacts, save_path))
        except Exception:
            pass

    # 1. Analysts
    analysts_dir = save_path / "1_analysts"
    analyst_parts = []
    if final_state.get("market_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "market.md").write_text(final_state["market_report"], encoding="utf-8")
        analyst_parts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "sentiment.md").write_text(final_state["sentiment_report"], encoding="utf-8")
        analyst_parts.append(("Social Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "news.md").write_text(final_state["news_report"], encoding="utf-8")
        analyst_parts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "fundamentals.md").write_text(final_state["fundamentals_report"], encoding="utf-8")
        analyst_parts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    # 2. Research
    if final_state.get("investment_debate_state"):
        research_dir = save_path / "2_research"
        debate = final_state["investment_debate_state"]
        research_parts = []
        if debate.get("bull_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bull.md").write_text(debate["bull_history"], encoding="utf-8")
            research_parts.append(("Bull Researcher", debate["bull_history"]))
        if debate.get("bear_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bear.md").write_text(debate["bear_history"], encoding="utf-8")
            research_parts.append(("Bear Researcher", debate["bear_history"]))
        if debate.get("judge_decision"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "manager.md").write_text(debate["judge_decision"], encoding="utf-8")
            research_parts.append(("Research Manager", debate["judge_decision"]))
        if research_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
            sections.append(f"## II. Research Team Decision\n\n{content}")

    # 3. Trading
    if final_state.get("trader_investment_plan"):
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(final_state["trader_investment_plan"], encoding="utf-8")
        sections.append(f"## III. Trading Team Plan\n\n### Trader\n{final_state['trader_investment_plan']}")

    # 4. Risk Management
    if final_state.get("risk_debate_state"):
        risk_dir = save_path / "4_risk"
        risk = final_state["risk_debate_state"]
        risk_parts = []
        if risk.get("aggressive_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "aggressive.md").write_text(risk["aggressive_history"], encoding="utf-8")
            risk_parts.append(("Aggressive Analyst", risk["aggressive_history"]))
        if risk.get("conservative_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "conservative.md").write_text(risk["conservative_history"], encoding="utf-8")
            risk_parts.append(("Conservative Analyst", risk["conservative_history"]))
        if risk.get("neutral_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "neutral.md").write_text(risk["neutral_history"], encoding="utf-8")
            risk_parts.append(("Neutral Analyst", risk["neutral_history"]))
        if risk_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
            sections.append(f"## IV. Risk Management Team Decision\n\n{content}")

        # 5. Portfolio Manager
        if risk.get("judge_decision"):
            portfolio_dir = save_path / "5_portfolio"
            portfolio_dir.mkdir(exist_ok=True)
            (portfolio_dir / "decision.md").write_text(risk["judge_decision"], encoding="utf-8")
            sections.append(f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{risk['judge_decision']}")

    # Write consolidated report
    header = f"# Trading Analysis Report: {ticker}\n\nGenerated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    complete_report = header + format_report_metadata(report_metadata) + "\n\n".join(sections)
    markdown_path = save_path / "complete_report.md"
    markdown_path.write_text(complete_report, encoding="utf-8")
    html = render_markdown_report_html(complete_report, f"Trading Analysis Report: {ticker}")
    (save_path / "complete_report.html").write_text(html, encoding="utf-8")
    write_pdf_report(
        complete_report,
        save_path / "complete_report.pdf",
        title=f"Trading Analysis Report: {ticker}",
        report_metadata=report_metadata,
        chart_artifacts=chart_artifacts,
    )
    return markdown_path


def display_complete_report(final_state):
    """Display the complete analysis report sequentially (avoids truncation)."""
    console.print()
    console.print(Rule("Complete Analysis Report", style="bold green"))

    # I. Analyst Team Reports
    analysts = []
    if final_state.get("market_report"):
        analysts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts.append(("Social Analyst", final_state["sentiment_report"]))
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


def update_research_team_status(message_buffer: MessageBuffer, status):
    """Update status for research team members (not Trader)."""
    research_team = ["Bull Researcher", "Bear Researcher", "Research Manager"]
    for agent in research_team:
        message_buffer.update_agent_status(agent, status)


# Ordered list of analysts for status transitions
ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "social": "Social Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
ANALYST_REPORT_MAP = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}


def update_analyst_statuses(message_buffer, chunk):
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
    if not found_active and selected:
        if message_buffer.agent_status.get("Bull Researcher") == "pending":
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

def _parse_analysts_option(value: str | None) -> list[AnalystType] | None:
    if value is None or not value.strip():
        return None

    if value.strip().lower() == "all":
        return list(AnalystType)

    analysts = []
    valid_values = {analyst.value for analyst in AnalystType}
    for raw_key in value.split(","):
        key = raw_key.strip().lower()
        if not key:
            continue
        if key not in valid_values:
            valid = ", ".join(sorted(valid_values))
            raise typer.BadParameter(f"Invalid analyst '{key}'. Valid values: {valid}")
        analysts.append(AnalystType(key))

    if not analysts:
        raise typer.BadParameter("At least one analyst must be provided.")
    return analysts


def _validate_research_depth(value: int | None) -> int | None:
    if value is None:
        return None
    if value not in (1, 3, 5):
        raise typer.BadParameter("Research depth must be one of: 1, 3, 5.")
    return value


def _validate_analysis_date_option(value: str | None) -> str | None:
    if value is None:
        return None
    if value.strip().lower() == "today":
        return datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        analysis_date = datetime.datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise typer.BadParameter("Analysis date must use YYYY-MM-DD format.") from exc
    if analysis_date.date() > datetime.datetime.now().date():
        raise typer.BadParameter("Analysis date cannot be in the future.")
    return value


def run_analysis(
    checkpoint: bool = False,
    llm_overrides: LLMConfigOverrides | None = None,
    selection_overrides: SelectionOverrides | None = None,
) -> AnalysisRunResult:
    # First get all user selections
    resolved_llm = resolve_llm_config(llm_overrides)
    selection_overrides = selection_overrides or SelectionOverrides()
    selections = get_user_selections(resolved_llm, selection_overrides)

    # Create config with selected research depth
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = selections["research_depth"]
    config["max_risk_discuss_rounds"] = selections["research_depth"]
    config["quick_think_llm"] = selections["shallow_thinker"]
    config["deep_think_llm"] = selections["deep_thinker"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()
    # Provider-specific thinking configuration
    config["google_thinking_level"] = selections.get("google_thinking_level")
    config["openai_reasoning_effort"] = selections.get("openai_reasoning_effort")
    config["anthropic_effort"] = selections.get("anthropic_effort")
    config["output_language"] = selections.get("output_language", "English")
    config["checkpoint_enabled"] = checkpoint
    llm_metadata = build_llm_report_metadata(selections)
    safe_ticker = normalize_ticker_symbol(selections["ticker"])
    selections["ticker"] = safe_ticker

    # Create stats callback handler for tracking LLM/tool calls
    stats_handler = StatsCallbackHandler()

    # Normalize analyst selection to predefined order (selection is a 'set', order is fixed)
    selected_set = {analyst.value for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]

    # Initialize the graph with callbacks bound to LLMs
    graph = TradingAgentsGraph(
        selected_analyst_keys,
        config=config,
        debug=True,
        callbacks=[stats_handler],
    )

    # Track start time for elapsed display
    start_time = time.time()

    # Create result directory
    results_dir = Path(cast(str, config["results_dir"])) / safe_ticker / selections["analysis_date"]
    results_dir.mkdir(parents=True, exist_ok=True)
    report_dir = results_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_file = results_dir / "message_tool.log"
    log_file.touch(exist_ok=True)

    message_buffer = MessageBuffer(logger=RunLogger(log_file, report_dir))
    message_buffer.init_for_analysis(selected_analyst_keys)

    # Now start the display layout
    layout = create_layout()

    with Live(layout, refresh_per_second=4):
        # Initial display
        update_display(layout, message_buffer, stats_handler=stats_handler, start_time=start_time)

        # Add initial messages
        message_buffer.add_message("System", f"Selected ticker: {selections['ticker']}")
        message_buffer.add_message(
            "System", f"Analysis date: {selections['analysis_date']}"
        )
        message_buffer.add_message(
            "System",
            f"Selected analysts: {', '.join(analyst.value for analyst in selections['analysts'])}",
        )
        message_buffer.add_message("System", format_llm_runtime_summary(llm_metadata))
        update_display(layout, message_buffer, stats_handler=stats_handler, start_time=start_time)

        # Update agent status to in_progress for the first analyst
        first_analyst = f"{selections['analysts'][0].value.capitalize()} Analyst"
        message_buffer.update_agent_status(first_analyst, "in_progress")
        update_display(layout, message_buffer, stats_handler=stats_handler, start_time=start_time)

        # Create spinner text
        spinner_text = (
            f"Analyzing {selections['ticker']} on {selections['analysis_date']}..."
        )
        update_display(layout, message_buffer, spinner_text, stats_handler=stats_handler, start_time=start_time)

        # Initialize state and get graph args with callbacks
        init_agent_state = graph.propagator.create_initial_state(
            selections["ticker"], selections["analysis_date"]
        )
        # Pass callbacks to graph config for tool execution tracking
        # (LLM tracking is handled separately via LLM constructor)
        args = graph.propagator.get_graph_args(callbacks=[stats_handler])

        # Stream the analysis
        trace = []
        for chunk in graph.graph.stream(init_agent_state, **args):
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
            update_analyst_statuses(message_buffer, chunk)

            # Research Team - Handle Investment Debate State
            if chunk.get("investment_debate_state"):
                debate_state = chunk["investment_debate_state"]
                bull_hist = debate_state.get("bull_history", "").strip()
                bear_hist = debate_state.get("bear_history", "").strip()
                judge = debate_state.get("judge_decision", "").strip()

                # Only update status when there's actual content
                if bull_hist or bear_hist:
                    update_research_team_status(message_buffer, "in_progress")
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
                    update_research_team_status(message_buffer, "completed")
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
                if judge:
                    if message_buffer.agent_status.get("Portfolio Manager") != "completed":
                        message_buffer.update_agent_status("Portfolio Manager", "in_progress")
                        message_buffer.update_report_section(
                            "final_trade_decision", f"### Portfolio Manager Decision\n{judge}"
                        )
                        message_buffer.update_agent_status("Aggressive Analyst", "completed")
                        message_buffer.update_agent_status("Conservative Analyst", "completed")
                        message_buffer.update_agent_status("Neutral Analyst", "completed")
                        message_buffer.update_agent_status("Portfolio Manager", "completed")

            # Update the display
            update_display(layout, message_buffer, stats_handler=stats_handler, start_time=start_time)

            trace.append(chunk)

        # Get final state and decision
        final_state = trace[-1]
        graph.process_signal(final_state["final_trade_decision"])

        # Update all agent statuses to completed
        for agent in message_buffer.agent_status:
            message_buffer.update_agent_status(agent, "completed")

        message_buffer.add_message(
            "System", f"Completed analysis for {selections['analysis_date']}"
        )

        # Update final report sections
        for section in message_buffer.report_sections.keys():
            if section in final_state:
                message_buffer.update_report_section(section, final_state[section])

        update_display(layout, message_buffer, stats_handler=stats_handler, start_time=start_time)

    # Post-analysis prompts (outside Live context for clean interaction)
    console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")

    # Prompt to save report unless configured by CLI.
    save_report = selection_overrides.save_report
    saved_report_path: Path | None = None
    resolved_save_path: Path | None = None
    if save_report is None:
        save_choice = typer.prompt("Save report?", default="Y").strip().upper()
        save_report = save_choice in ("Y", "YES", "")
    if save_report:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = Path.cwd() / "reports" / f"{selections['ticker']}_{timestamp}"
        save_path = selection_overrides.save_path
        if save_path is None:
            if selection_overrides.save_report is True:
                save_path = default_path
            else:
                save_path_str = typer.prompt(
                    "Save path (press Enter for default)",
                    default=str(default_path)
                ).strip()
                save_path = Path(save_path_str)
        try:
            report_file = save_report_to_disk(
                final_state,
                selections["ticker"],
                save_path,
                report_metadata=llm_metadata,
            )
            console.print(f"\n[green]✓ Report saved to:[/green] {save_path.resolve()}")
            console.print(f"  [dim]Complete report:[/dim] {report_file.name}")
            console.print(f"  [dim]HTML report:[/dim] {report_file.with_suffix('.html').name}")
            saved_report_path = report_file
            resolved_save_path = save_path
        except Exception as e:
            console.print(f"[red]Error saving report: {e}[/red]")

    # Prompt to display full report unless configured by CLI.
    display_report = selection_overrides.display_report
    if display_report is None:
        display_choice = typer.prompt("\nDisplay full report on screen?", default="Y").strip().upper()
        display_report = display_choice in ("Y", "YES", "")
    if display_report:
        display_complete_report(final_state)

    return AnalysisRunResult(
        ticker=selections["ticker"],
        final_state=final_state,
        report_path=saved_report_path,
        save_path=resolved_save_path,
    )


@app.command()
def analyze(
    checkpoint: bool = typer.Option(
        False,
        "--checkpoint",
        help="Enable checkpoint/resume: save state after each node so a crashed run can resume.",
    ),
    clear_checkpoints: bool = typer.Option(
        False,
        "--clear-checkpoints",
        help="Delete all saved checkpoints before running (force fresh start).",
    ),
    ticker: str | None = typer.Option(
        None,
        "--ticker",
        help="Ticker symbol to analyze, e.g. SPY or CNC.TO.",
    ),
    analysis_date: str | None = typer.Option(
        None,
        "--analysis-date",
        help="Analysis date in YYYY-MM-DD format, or 'today'.",
    ),
    output_language: str | None = typer.Option(
        None,
        "--output-language",
        help="Language for analyst reports and final decision, e.g. English, Spanish, Chinese.",
    ),
    analysts: str | None = typer.Option(
        None,
        "--analysts",
        help="Comma-separated analyst keys: market,social,news,fundamentals; or 'all'.",
    ),
    research_depth: int | None = typer.Option(
        None,
        "--research-depth",
        help="Research depth, e.g. 1=shallow, 3=medium, 5=deep.",
    ),
    llm_provider: str | None = typer.Option(
        None,
        "--llm-provider",
        help="LLM provider key, e.g. openai.",
    ),
    quick_model: str | None = typer.Option(
        None,
        "--quick-model",
        help="Model for quick-thinking agents.",
    ),
    deep_model: str | None = typer.Option(
        None,
        "--deep-model",
        help="Model for deep-thinking agents.",
    ),
    backend_url: str | None = typer.Option(
        None,
        "--backend-url",
        help="OpenAI-compatible base URL.",
    ),
    openai_reasoning_effort: str | None = typer.Option(
        None,
        "--openai-reasoning-effort",
        help="OpenAI reasoning effort.",
    ),
    google_thinking_level: str | None = typer.Option(
        None,
        "--google-thinking-level",
        help="Gemini thinking level.",
    ),
    anthropic_effort: str | None = typer.Option(
        None,
        "--anthropic-effort",
        help="Anthropic effort level.",
    ),
    save_report: bool | None = typer.Option(
        None,
        "--save-report/--no-save-report",
        help="Save the final report after analysis.",
    ),
    save_path: Path | None = typer.Option(
        None,
        "--save-path",
        help="Directory where the report should be saved.",
    ),
    display_report: bool | None = typer.Option(
        None,
        "--display-report/--no-display-report",
        help="Display the full report on screen after analysis.",
    ),
):
    if clear_checkpoints:
        from tradingagents.graph.checkpointer import clear_all_checkpoints
        n = clear_all_checkpoints(cast(str, DEFAULT_CONFIG["data_cache_dir"]))
        console.print(f"[yellow]Cleared {n} checkpoint(s).[/yellow]")
    run_analysis(
        checkpoint=checkpoint,
        llm_overrides=LLMConfigOverrides(
            provider=llm_provider,
            quick_model=quick_model,
            deep_model=deep_model,
            backend_url=backend_url,
            openai_reasoning_effort=openai_reasoning_effort,
            google_thinking_level=google_thinking_level,
            anthropic_effort=anthropic_effort,
        ),
        selection_overrides=SelectionOverrides(
            ticker=normalize_ticker_symbol(ticker) if ticker else None,
            analysis_date=_validate_analysis_date_option(analysis_date),
            output_language=output_language,
            analysts=_parse_analysts_option(analysts),
            research_depth=_validate_research_depth(research_depth),
            save_report=save_report,
            save_path=save_path,
            display_report=display_report,
        ),
    )


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    checkpoint: bool = typer.Option(
        False,
        "--checkpoint",
        help="Enable checkpoint/resume: save state after each node so a crashed run can resume.",
    ),
    clear_checkpoints: bool = typer.Option(
        False,
        "--clear-checkpoints",
        help="Delete all saved checkpoints before running (force fresh start).",
    ),
    ticker: str | None = typer.Option(
        None,
        "--ticker",
        help="Ticker symbol to analyze, e.g. SPY or CNC.TO.",
    ),
    analysis_date: str | None = typer.Option(
        None,
        "--analysis-date",
        help="Analysis date in YYYY-MM-DD format, or 'today'.",
    ),
    output_language: str | None = typer.Option(
        None,
        "--output-language",
        help="Language for analyst reports and final decision.",
    ),
    analysts: str | None = typer.Option(
        None,
        "--analysts",
        help="Comma-separated analyst keys: market,social,news,fundamentals; or 'all'.",
    ),
    research_depth: int | None = typer.Option(
        None,
        "--research-depth",
        help="Research depth, e.g. 1=shallow, 3=medium, 5=deep.",
    ),
    llm_provider: str | None = typer.Option(
        None,
        "--llm-provider",
        help="LLM provider key, e.g. openai.",
    ),
    quick_model: str | None = typer.Option(
        None,
        "--quick-model",
        help="Model for quick-thinking agents.",
    ),
    deep_model: str | None = typer.Option(
        None,
        "--deep-model",
        help="Model for deep-thinking agents.",
    ),
    backend_url: str | None = typer.Option(
        None,
        "--backend-url",
        help="OpenAI-compatible base URL.",
    ),
    openai_reasoning_effort: str | None = typer.Option(
        None,
        "--openai-reasoning-effort",
        help="OpenAI reasoning effort.",
    ),
    google_thinking_level: str | None = typer.Option(
        None,
        "--google-thinking-level",
        help="Gemini thinking level.",
    ),
    anthropic_effort: str | None = typer.Option(
        None,
        "--anthropic-effort",
        help="Anthropic effort level.",
    ),
    save_report: bool | None = typer.Option(
        None,
        "--save-report/--no-save-report",
        help="Save the final report after analysis.",
    ),
    save_path: Path | None = typer.Option(
        None,
        "--save-path",
        help="Directory where the report should be saved.",
    ),
    display_report: bool | None = typer.Option(
        None,
        "--display-report/--no-display-report",
        help="Display the full report on screen after analysis.",
    ),
):
    if ctx.invoked_subcommand is not None:
        return
    analyze(
        checkpoint=checkpoint,
        clear_checkpoints=clear_checkpoints,
        ticker=ticker,
        analysis_date=analysis_date,
        output_language=output_language,
        analysts=analysts,
        research_depth=research_depth,
        llm_provider=llm_provider,
        quick_model=quick_model,
        deep_model=deep_model,
        backend_url=backend_url,
        openai_reasoning_effort=openai_reasoning_effort,
        google_thinking_level=google_thinking_level,
        anthropic_effort=anthropic_effort,
        save_report=save_report,
        save_path=save_path,
        display_report=display_report,
    )


@app.command("batch")
def batch_command(
    input_path: Path | None = typer.Option(
        None,
        "--input",
        help="CSV or JSON portfolio/watchlist file. CSV/JSON must include ticker.",
    ),
    tickers: str | None = typer.Option(
        None,
        "--tickers",
        help="Comma-separated tickers, e.g. AAPL,MSFT,NVDA.",
    ),
    checkpoint: bool = typer.Option(
        False,
        "--checkpoint",
        help="Enable checkpoint/resume for each ticker.",
    ),
    analysis_date: str | None = typer.Option(
        None,
        "--analysis-date",
        help="Analysis date in YYYY-MM-DD format, or 'today'.",
    ),
    output_language: str = typer.Option(
        "English",
        "--output-language",
        help="Language for analyst reports and final decision.",
    ),
    analysts: str = typer.Option(
        "all",
        "--analysts",
        help="Comma-separated analyst keys: market,social,news,fundamentals; or 'all'.",
    ),
    research_depth: int = typer.Option(
        1,
        "--research-depth",
        help="Research depth: 1, 3, or 5.",
    ),
    llm_provider: str | None = typer.Option(
        None,
        "--llm-provider",
        help="LLM provider key, e.g. openai.",
    ),
    quick_model: str | None = typer.Option(
        None,
        "--quick-model",
        help="Model for quick-thinking agents.",
    ),
    deep_model: str | None = typer.Option(
        None,
        "--deep-model",
        help="Model for deep-thinking agents.",
    ),
    backend_url: str | None = typer.Option(
        None,
        "--backend-url",
        help="OpenAI-compatible base URL.",
    ),
    openai_reasoning_effort: str | None = typer.Option(
        None,
        "--openai-reasoning-effort",
        help="OpenAI reasoning effort.",
    ),
    google_thinking_level: str | None = typer.Option(
        None,
        "--google-thinking-level",
        help="Gemini thinking level.",
    ),
    anthropic_effort: str | None = typer.Option(
        None,
        "--anthropic-effort",
        help="Anthropic effort level.",
    ),
    save_path: Path | None = typer.Option(
        None,
        "--save-path",
        help="Batch output directory.",
    ),
    display_report: bool = typer.Option(
        False,
        "--display-report/--no-display-report",
        help="Display each full per-ticker report after analysis.",
    ),
    continue_on_error: bool = typer.Option(
        True,
        "--continue-on-error/--fail-fast",
        help="Continue after a per-ticker failure, or stop at the first failure.",
    ),
    cash: float = typer.Option(
        0.0,
        "--cash",
        help="Available cash to include in allocation planning.",
    ),
    allocate: bool = typer.Option(
        False,
        "--allocate/--no-allocate",
        help="Generate portfolio allocation recommendations.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show proposed paper orders without submitting anything.",
    ),
    max_position_weight: float = typer.Option(
        0.25,
        "--max-position-weight",
        help="Maximum target weight per ticker, e.g. 0.25.",
    ),
    min_cash_weight: float = typer.Option(
        0.0,
        "--min-cash-weight",
        help="Minimum target cash weight, e.g. 0.05.",
    ),
):
    try:
        holdings = load_batch_inputs(input_path=input_path, tickers=tickers)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if cash < 0:
        raise typer.BadParameter("cash must be non-negative.")
    if not 0 <= max_position_weight <= 1:
        raise typer.BadParameter("max-position-weight must be between 0 and 1.")
    if not 0 <= min_cash_weight <= 1:
        raise typer.BadParameter("min-cash-weight must be between 0 and 1.")
    if dry_run:
        allocate = True

    if analysis_date:
        validated_batch_date = _validate_analysis_date_option(analysis_date)
        assert validated_batch_date is not None
        batch_date = validated_batch_date
    else:
        batch_date = datetime.datetime.now().strftime("%Y-%m-%d")
    parsed_analysts = _parse_analysts_option(analysts) or list(AnalystType)
    parsed_depth = _validate_research_depth(research_depth)
    if parsed_depth is None:
        parsed_depth = 1
    if save_path is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = Path.cwd() / "reports" / f"batch_{timestamp}"

    run_batch_analysis(
        holdings=holdings,
        analysis_date=batch_date,
        output_language=output_language,
        analysts=parsed_analysts,
        research_depth=parsed_depth,
        checkpoint=checkpoint,
        llm_overrides=LLMConfigOverrides(
            provider=llm_provider,
            quick_model=quick_model,
            deep_model=deep_model,
            backend_url=backend_url,
            openai_reasoning_effort=openai_reasoning_effort,
            google_thinking_level=google_thinking_level,
            anthropic_effort=anthropic_effort,
        ),
        save_path=save_path,
        display_report=display_report,
        continue_on_error=continue_on_error,
        available_cash=cash,
        allocate=allocate,
        dry_run=dry_run,
        allocation_policy=AllocationPolicy(
            max_position_weight=max_position_weight,
            min_cash_weight=min_cash_weight,
        ),
        prices=None,
    )


if __name__ == "__main__":
    app()
