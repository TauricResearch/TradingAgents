from typing import Optional
import datetime
import json
from tradingagents.agents.utils.json_utils import extract_json
import typer
from pathlib import Path
from functools import wraps
from rich.console import Console
from dotenv import load_dotenv

# Load environment variables from .env file.
# Checks CWD first, then falls back to project root (relative to this script).
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live
from rich.markdown import Markdown
from rich.layout import Layout
from rich.text import Text
from rich.table import Table
from collections import deque
import time
from rich import box
from rich.align import Align
from rich.rule import Rule

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.report_paths import get_daily_dir, get_market_dir, get_ticker_dir
from tradingagents.daily_digest import append_to_digest
from tradingagents.notebook_sync import sync_to_notebooklm
from tradingagents.default_config import DEFAULT_CONFIG
from cli.utils import *
from tradingagents.graph.scanner_graph import ScannerGraph
from cli.announcements import fetch_announcements, display_announcements
from cli.stats_handler import StatsCallbackHandler
from tradingagents.observability import RunLogger, set_run_logger
from tradingagents.api_usage import format_vendor_breakdown, format_av_assessment

console = Console()

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
        "Risk Management": [
            "Aggressive Analyst",
            "Neutral Analyst",
            "Conservative Analyst",
        ],
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

    def __init__(self, max_length=100):
        self.messages = deque(maxlen=max_length)
        self.tool_calls = deque(maxlen=max_length)
        self.current_report = None
        self.final_report = None  # Store the complete final report
        self.agent_status = {}
        self.current_agent = None
        self.report_sections = {}
        self.selected_analysts = []
        self._last_message_id = None

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
        self._last_message_id = None

    def get_completed_reports_count(self):
        """Count reports that are finalized (their finalizing agent is completed).

        A report is considered complete when:
        1. The report section has content (not None), AND
        2. The agent responsible for finalizing that report has status "completed"

        This prevents interim updates (like debate rounds) from counting as completed.
        """
        count = 0
        for section, (_, finalizing_agent) in self.REPORT_SECTIONS.items():
            if self.report_sections.get(section) is not None:
                if self.agent_status.get(finalizing_agent) == "completed":
                    count += 1
        return count

    def add_message(self, message_type, content):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.messages.append((timestamp, message_type, content))

    def add_tool_call(self, tool_name, args):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.tool_calls.append((timestamp, tool_name, args))

    def update_agent_status(self, agent, status):
        if agent in self.agent_status:
            self.agent_status[agent] = status
            self.current_agent = agent

    def update_report_section(self, section_name, content):
        if section_name in self.report_sections:
            self.report_sections[section_name] = content
            self._update_current_report()

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
        analyst_sections = [
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
        ]
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
        return f"{n / 1000:.1f}k"
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
            "Social Analyst",
            "News Analyst",
            "Fundamentals Analyst",
        ],
        "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
        "Trading Team": ["Trader"],
        "Risk Management": [
            "Aggressive Analyst",
            "Neutral Analyst",
            "Conservative Analyst",
        ],
        "Portfolio Management": ["Portfolio Manager"],
    }

    # Filter teams to only include agents that are in agent_status
    teams = {}
    active_agent_status_keys = set(message_buffer.agent_status.keys())
    for team, agents in all_teams.items():
        active_agents = [a for a in agents if a in active_agent_status_keys]
        if active_agents:
            teams[team] = active_agents

    for team, agents in teams.items():
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


def _ask_provider_thinking_config(provider: str):
    """Ask for provider-specific thinking config. Returns (thinking_level, reasoning_effort)."""
    provider_lower = provider.lower()
    if provider_lower == "google":
        return ask_gemini_thinking_config(), None
    elif provider_lower in ("openai", "xai"):
        return None, ask_openai_reasoning_effort()
    return None, None


def get_user_selections():
    """Get all user selections before starting the analysis display."""
    # Display ASCII art welcome message
    with open("./cli/static/welcome.txt", "r", encoding="utf-8") as f:
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

    # Step 1: Ticker symbol
    console.print(
        create_question_box(
            "Step 1: Ticker Symbol", "Enter the ticker symbol to analyze", "SPY"
        )
    )
    selected_ticker = get_ticker()

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

    # Step 3: Select analysts
    console.print(
        create_question_box(
            "Step 3: Analysts Team", "Select your LLM analyst agents for the analysis"
        )
    )
    selected_analysts = select_analysts()
    console.print(
        f"[green]Selected analysts:[/green] {', '.join(analyst.value for analyst in selected_analysts)}"
    )

    # Step 4: Research depth
    console.print(
        create_question_box(
            "Step 4: Research Depth", "Select your research depth level"
        )
    )
    selected_research_depth = select_research_depth()

    # Step 5: Quick-thinking provider + model
    console.print(
        create_question_box(
            "Step 5: Quick-Thinking Setup",
            "Provider and model for analysts & risk debaters (fast, high volume)",
        )
    )
    quick_provider, quick_backend_url = select_llm_provider()
    selected_shallow_thinker = select_shallow_thinking_agent(quick_provider)
    quick_thinking_level, quick_reasoning_effort = _ask_provider_thinking_config(
        quick_provider
    )

    # Step 6: Mid-thinking provider + model
    console.print(
        create_question_box(
            "Step 6: Mid-Thinking Setup",
            "Provider and model for researchers & trader (reasoning, argument formation)",
        )
    )
    mid_provider, mid_backend_url = select_llm_provider()
    selected_mid_thinker = select_mid_thinking_agent(mid_provider)
    mid_thinking_level, mid_reasoning_effort = _ask_provider_thinking_config(
        mid_provider
    )

    # Step 7: Deep-thinking provider + model
    console.print(
        create_question_box(
            "Step 7: Deep-Thinking Setup",
            "Provider and model for investment judge & risk manager (final decisions)",
        )
    )
    deep_provider, deep_backend_url = select_llm_provider()
    selected_deep_thinker = select_deep_thinking_agent(deep_provider)
    deep_thinking_level, deep_reasoning_effort = _ask_provider_thinking_config(
        deep_provider
    )

    return {
        "ticker": selected_ticker,
        "analysis_date": analysis_date,
        "analysts": selected_analysts,
        "research_depth": selected_research_depth,
        # Quick
        "quick_provider": quick_provider.lower(),
        "quick_backend_url": quick_backend_url,
        "shallow_thinker": selected_shallow_thinker,
        "quick_thinking_level": quick_thinking_level,
        "quick_reasoning_effort": quick_reasoning_effort,
        # Mid
        "mid_provider": mid_provider.lower(),
        "mid_backend_url": mid_backend_url,
        "mid_thinker": selected_mid_thinker,
        "mid_thinking_level": mid_thinking_level,
        "mid_reasoning_effort": mid_reasoning_effort,
        # Deep
        "deep_provider": deep_provider.lower(),
        "deep_backend_url": deep_backend_url,
        "deep_thinker": selected_deep_thinker,
        "deep_thinking_level": deep_thinking_level,
        "deep_reasoning_effort": deep_reasoning_effort,
    }


def save_report_to_disk(final_state, ticker: str, save_path: Path):
    """Save complete analysis report to disk with organized subfolders."""
    save_path.mkdir(parents=True, exist_ok=True)
    sections = []

    # 1. Analysts
    analysts_dir = save_path / "1_analysts"
    analyst_parts = []
    if final_state.get("market_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "market.md").write_text(final_state["market_report"])
        analyst_parts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "sentiment.md").write_text(final_state["sentiment_report"])
        analyst_parts.append(("Social Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "news.md").write_text(final_state["news_report"])
        analyst_parts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "fundamentals.md").write_text(
            final_state["fundamentals_report"]
        )
        analyst_parts.append(
            ("Fundamentals Analyst", final_state["fundamentals_report"])
        )
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
            (research_dir / "bull.md").write_text(debate["bull_history"])
            research_parts.append(("Bull Researcher", debate["bull_history"]))
        if debate.get("bear_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bear.md").write_text(debate["bear_history"])
            research_parts.append(("Bear Researcher", debate["bear_history"]))
        if debate.get("judge_decision"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "manager.md").write_text(debate["judge_decision"])
            research_parts.append(("Research Manager", debate["judge_decision"]))
        if research_parts:
            content = "\n\n".join(
                f"### {name}\n{text}" for name, text in research_parts
            )
            sections.append(f"## II. Research Team Decision\n\n{content}")

    # 3. Trading
    if final_state.get("trader_investment_plan"):
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(final_state["trader_investment_plan"])
        sections.append(
            f"## III. Trading Team Plan\n\n### Trader\n{final_state['trader_investment_plan']}"
        )

    # 4. Risk Management
    if final_state.get("risk_debate_state"):
        risk_dir = save_path / "4_risk"
        risk = final_state["risk_debate_state"]
        risk_parts = []
        if risk.get("aggressive_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "aggressive.md").write_text(risk["aggressive_history"])
            risk_parts.append(("Aggressive Analyst", risk["aggressive_history"]))
        if risk.get("conservative_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "conservative.md").write_text(risk["conservative_history"])
            risk_parts.append(("Conservative Analyst", risk["conservative_history"]))
        if risk.get("neutral_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "neutral.md").write_text(risk["neutral_history"])
            risk_parts.append(("Neutral Analyst", risk["neutral_history"]))
        if risk_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
            sections.append(f"## IV. Risk Management Team Decision\n\n{content}")

        # 5. Portfolio Manager
        if risk.get("judge_decision"):
            portfolio_dir = save_path / "5_portfolio"
            portfolio_dir.mkdir(exist_ok=True)
            (portfolio_dir / "decision.md").write_text(risk["judge_decision"])
            sections.append(
                f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{risk['judge_decision']}"
            )

    # Write consolidated report
    header = f"# Trading Analysis Report: {ticker}\n\nGenerated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    (save_path / "complete_report.md").write_text(header + "\n\n".join(sections))
    return save_path / "complete_report.md"


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
        console.print(
            Panel("[bold]I. Analyst Team Reports[/bold]", border_style="cyan")
        )
        for title, content in analysts:
            console.print(
                Panel(
                    Markdown(content), title=title, border_style="blue", padding=(1, 2)
                )
            )

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
            console.print(
                Panel("[bold]II. Research Team Decision[/bold]", border_style="magenta")
            )
            for title, content in research:
                console.print(
                    Panel(
                        Markdown(content),
                        title=title,
                        border_style="blue",
                        padding=(1, 2),
                    )
                )

    # III. Trading Team
    if final_state.get("trader_investment_plan"):
        console.print(
            Panel("[bold]III. Trading Team Plan[/bold]", border_style="yellow")
        )
        console.print(
            Panel(
                Markdown(final_state["trader_investment_plan"]),
                title="Trader",
                border_style="blue",
                padding=(1, 2),
            )
        )

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
            console.print(
                Panel(
                    "[bold]IV. Risk Management Team Decision[/bold]", border_style="red"
                )
            )
            for title, content in risk_reports:
                console.print(
                    Panel(
                        Markdown(content),
                        title=title,
                        border_style="blue",
                        padding=(1, 2),
                    )
                )

        # V. Portfolio Manager Decision
        if risk.get("judge_decision"):
            console.print(
                Panel(
                    "[bold]V. Portfolio Manager Decision[/bold]", border_style="green"
                )
            )
            console.print(
                Panel(
                    Markdown(risk["judge_decision"]),
                    title="Portfolio Manager",
                    border_style="blue",
                    padding=(1, 2),
                )
            )


def update_research_team_status(status):
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
    """Update all analyst statuses based on current report state.

    Logic:
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
        has_report = bool(chunk.get(report_key))

        if has_report:
            message_buffer.update_agent_status(agent_name, "completed")
            message_buffer.update_report_section(report_key, chunk[report_key])
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
        if val is None or val == "":
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
        text = content.get("text", "")
        return text.strip() if not is_empty(text) else None

    if isinstance(content, list):
        text_parts = [
            item.get("text", "").strip()
            if isinstance(item, dict) and item.get("type") == "text"
            else (item.strip() if isinstance(item, str) else "")
            for item in content
        ]
        result = " ".join(t for t in text_parts if t and not is_empty(t))
        return result if result else None

    return str(content).strip() if not is_empty(content) else None


def classify_message_type(message) -> tuple[str, str | None]:
    """Classify LangChain message into display type and extract content.

    Returns:
        (type, content) - type is one of: User, Agent, Data, Control
                        - content is extracted string or None
    """
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    content = extract_content_string(getattr(message, "content", None))

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


def parse_tool_call(tool_call) -> tuple[str, dict | str]:
    """Parse a tool call into a name and arguments dictionary.
    Handles dicts, objects with name/args attributes, and string representations.
    """
    import ast

    if isinstance(tool_call, dict):
        tool_name = tool_call.get("name", "Unknown Tool")
        args = tool_call.get("args", tool_call.get("arguments", {}))
        return tool_name, args

    if isinstance(tool_call, str):
        try:
            tool_call_dict = ast.literal_eval(tool_call)
            if not isinstance(tool_call_dict, dict):
                tool_call_dict = {}
        except (ValueError, SyntaxError):
            tool_call_dict = {}

        tool_name = tool_call_dict.get("name", "Unknown Tool")
        args = tool_call_dict.get("args", tool_call_dict.get("arguments", {}))
        return tool_name, args

    # Fallback for objects with name and args attributes
    tool_name = getattr(tool_call, "name", "Unknown Tool")
    args = getattr(tool_call, "args", getattr(tool_call, "arguments", {}))
    return tool_name, args


def format_tool_args(args, max_length=80) -> str:
    """Format tool arguments for terminal display."""
    result = str(args)
    if len(result) > max_length:
        return result[: max_length - 3] + "..."
    return result


def run_analysis():
    # First get all user selections
    selections = get_user_selections()

    # Create config with selected research depth
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = selections["research_depth"]
    config["max_risk_discuss_rounds"] = selections["research_depth"]
    # Per-role LLM configuration
    config["quick_think_llm"] = selections["shallow_thinker"]
    config["quick_think_llm_provider"] = selections["quick_provider"]
    config["quick_think_backend_url"] = selections["quick_backend_url"]
    config["quick_think_google_thinking_level"] = selections.get("quick_thinking_level")
    config["quick_think_openai_reasoning_effort"] = selections.get(
        "quick_reasoning_effort"
    )
    config["mid_think_llm"] = selections["mid_thinker"]
    config["mid_think_llm_provider"] = selections["mid_provider"]
    config["mid_think_backend_url"] = selections["mid_backend_url"]
    config["mid_think_google_thinking_level"] = selections.get("mid_thinking_level")
    config["mid_think_openai_reasoning_effort"] = selections.get("mid_reasoning_effort")
    config["deep_think_llm"] = selections["deep_thinker"]
    config["deep_think_llm_provider"] = selections["deep_provider"]
    config["deep_think_backend_url"] = selections["deep_backend_url"]
    config["deep_think_google_thinking_level"] = selections.get("deep_thinking_level")
    config["deep_think_openai_reasoning_effort"] = selections.get(
        "deep_reasoning_effort"
    )
    # Keep shared llm_provider/backend_url as a fallback (use quick as default)
    config["llm_provider"] = selections["quick_provider"]
    config["backend_url"] = selections["quick_backend_url"]

    # Create stats callback handler for tracking LLM/tool calls
    stats_handler = StatsCallbackHandler()
    run_logger = RunLogger()
    set_run_logger(run_logger)

    # Normalize analyst selection to predefined order (selection is a 'set', order is fixed)
    selected_set = {analyst.value for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]

    # Initialize the graph with callbacks bound to LLMs
    graph = TradingAgentsGraph(
        selected_analyst_keys,
        config=config,
        debug=True,
        callbacks=[stats_handler, run_logger.callback],
    )

    # Initialize message buffer with selected analysts
    message_buffer.init_for_analysis(selected_analyst_keys)

    # Track start time for elapsed display
    start_time = time.time()

    # Create result directory
    results_dir = get_ticker_dir(selections["analysis_date"], selections["ticker"])
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
            if (
                section_name in obj.report_sections
                and obj.report_sections[section_name] is not None
            ):
                content = obj.report_sections[section_name]
                if content:
                    file_name = f"{section_name}.md"
                    with open(report_dir / file_name, "w", encoding="utf-8") as f:
                        f.write(content)

        return wrapper

    message_buffer.add_message = save_message_decorator(message_buffer, "add_message")
    message_buffer.add_tool_call = save_tool_call_decorator(
        message_buffer, "add_tool_call"
    )
    message_buffer.update_report_section = save_report_section_decorator(
        message_buffer, "update_report_section"
    )

    # Now start the display layout
    layout = create_layout()

    with Live(layout, refresh_per_second=4) as live:
        # Initial display
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # Add initial messages
        message_buffer.add_message("System", f"Selected ticker: {selections['ticker']}")
        message_buffer.add_message(
            "System", f"Analysis date: {selections['analysis_date']}"
        )
        message_buffer.add_message(
            "System",
            f"Selected analysts: {', '.join(analyst.value for analyst in selections['analysts'])}",
        )
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # Update agent status to in_progress for the first analyst
        first_analyst = f"{selections['analysts'][0].value.capitalize()} Analyst"
        message_buffer.update_agent_status(first_analyst, "in_progress")
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # Create spinner text
        spinner_text = (
            f"Analyzing {selections['ticker']} on {selections['analysis_date']}..."
        )
        update_display(
            layout, spinner_text, stats_handler=stats_handler, start_time=start_time
        )

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
            # Process messages if present (skip duplicates via message ID)
            if len(chunk["messages"]) > 0:
                last_message = chunk["messages"][-1]
                msg_id = getattr(last_message, "id", None)

                if msg_id != message_buffer._last_message_id:
                    message_buffer._last_message_id = msg_id

                    # Add message to buffer
                    msg_type, content = classify_message_type(last_message)
                    if content and content.strip():
                        message_buffer.add_message(msg_type, content)

                    # Handle tool calls
                    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                        for tool_call in last_message.tool_calls:
                            tool_name, tool_args = parse_tool_call(tool_call)
                            message_buffer.add_tool_call(tool_name, tool_args)

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
                    message_buffer.update_agent_status(
                        "Aggressive Analyst", "in_progress"
                    )

            # Risk Management Team - Handle Risk Debate State
            if chunk.get("risk_debate_state"):
                risk_state = chunk["risk_debate_state"]
                agg_hist = risk_state.get("aggressive_history", "").strip()
                con_hist = risk_state.get("conservative_history", "").strip()
                neu_hist = risk_state.get("neutral_history", "").strip()
                judge = risk_state.get("judge_decision", "").strip()

                if agg_hist:
                    if (
                        message_buffer.agent_status.get("Aggressive Analyst")
                        != "completed"
                    ):
                        message_buffer.update_agent_status(
                            "Aggressive Analyst", "in_progress"
                        )
                    message_buffer.update_report_section(
                        "final_trade_decision",
                        f"### Aggressive Analyst Analysis\n{agg_hist}",
                    )
                if con_hist:
                    if (
                        message_buffer.agent_status.get("Conservative Analyst")
                        != "completed"
                    ):
                        message_buffer.update_agent_status(
                            "Conservative Analyst", "in_progress"
                        )
                    message_buffer.update_report_section(
                        "final_trade_decision",
                        f"### Conservative Analyst Analysis\n{con_hist}",
                    )
                if neu_hist:
                    if (
                        message_buffer.agent_status.get("Neutral Analyst")
                        != "completed"
                    ):
                        message_buffer.update_agent_status(
                            "Neutral Analyst", "in_progress"
                        )
                    message_buffer.update_report_section(
                        "final_trade_decision",
                        f"### Neutral Analyst Analysis\n{neu_hist}",
                    )
                if judge:
                    if (
                        message_buffer.agent_status.get("Portfolio Manager")
                        != "completed"
                    ):
                        message_buffer.update_agent_status(
                            "Portfolio Manager", "in_progress"
                        )
                        message_buffer.update_report_section(
                            "final_trade_decision",
                            f"### Portfolio Manager Decision\n{judge}",
                        )
                        message_buffer.update_agent_status(
                            "Aggressive Analyst", "completed"
                        )
                        message_buffer.update_agent_status(
                            "Conservative Analyst", "completed"
                        )
                        message_buffer.update_agent_status(
                            "Neutral Analyst", "completed"
                        )
                        message_buffer.update_agent_status(
                            "Portfolio Manager", "completed"
                        )

            # Update the display
            update_display(layout, stats_handler=stats_handler, start_time=start_time)

            trace.append(chunk)

        # Get final state and decision
        final_state = trace[-1]
        decision = graph.process_signal(final_state["final_trade_decision"])

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

        update_display(layout, stats_handler=stats_handler, start_time=start_time)

    # Post-analysis prompts (outside Live context for clean interaction)
    console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")

    # Prompt to save report
    save_choice = typer.prompt("Save report?", default="Y").strip().upper()
    if save_choice in ("Y", "YES", ""):
        default_path = get_ticker_dir(selections["analysis_date"], selections["ticker"])
        save_path_str = typer.prompt(
            "Save path (press Enter for default)", default=str(default_path)
        ).strip()
        save_path = Path(save_path_str)
        try:
            report_file = save_report_to_disk(
                final_state, selections["ticker"], save_path
            )
            console.print(f"\n[green]✓ Report saved to:[/green] {save_path.resolve()}")
            console.print(f"  [dim]Complete report:[/dim] {report_file.name}")
        except Exception as e:
            console.print(f"[red]Error saving report: {e}[/red]")

    # Append to daily digest and sync to NotebookLM
    digest_content = message_buffer.final_report or ""
    if digest_content:
        digest_path = append_to_digest(
            selections["analysis_date"], "analyze", selections["ticker"], digest_content
        )
        sync_to_notebooklm(digest_path, selections["analysis_date"])

    # Write observability log
    log_dir = get_ticker_dir(selections["analysis_date"], selections["ticker"])
    log_dir.mkdir(parents=True, exist_ok=True)
    run_logger.write_log(log_dir / "run_log.jsonl")
    summary = run_logger.summary()
    vendor_breakdown = format_vendor_breakdown(summary)
    av_assessment = format_av_assessment(summary)
    console.print(
        f"[dim]LLM calls: {summary['llm_calls']} | "
        f"Tokens: {summary['tokens_in']}→{summary['tokens_out']} | "
        f"Tools: {summary['tool_calls']} | "
        f"Vendor calls: {summary['vendor_success']}ok/{summary['vendor_fail']}fail[/dim]"
    )
    if vendor_breakdown:
        console.print(f"[dim]  Vendors: {vendor_breakdown}[/dim]")
    console.print(f"[dim]  {av_assessment}[/dim]")
    set_run_logger(None)

    # Prompt to display full report
    display_choice = (
        typer.prompt("\nDisplay full report on screen?", default="Y").strip().upper()
    )
    if display_choice in ("Y", "YES", ""):
        display_complete_report(final_state)


def run_scan(date: Optional[str] = None):
    """Run the 3-phase LLM scanner pipeline via ScannerGraph."""
    console.print(
        Panel("[bold green]Global Macro Scanner[/bold green]", border_style="green")
    )
    if date:
        scan_date = date
    else:
        default_date = datetime.datetime.now().strftime("%Y-%m-%d")
        scan_date = typer.prompt("Scan date (YYYY-MM-DD)", default=default_date)

    # Prepare save directory
    save_dir = get_market_dir(scan_date)
    save_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[cyan]Running 3-phase macro scanner for {scan_date}...[/cyan]")
    console.print(
        "[dim]Phase 1: Geopolitical + Market Movers + Sector scans (parallel)[/dim]"
    )
    console.print("[dim]Phase 2: Industry Deep Dive[/dim]")
    console.print("[dim]Phase 3: Macro Synthesis → stocks to investigate[/dim]\n")

    run_logger = RunLogger()
    set_run_logger(run_logger)

    try:
        scanner = ScannerGraph(
            config=DEFAULT_CONFIG.copy(), callbacks=[run_logger.callback]
        )
        with Live(Spinner("dots", text="Scanning..."), console=console, transient=True):
            result = scanner.scan(scan_date)
    except Exception as e:
        console.print(f"[red]Scanner failed: {e}[/red]")
        raise typer.Exit(1)

    # Save reports
    for key in [
        "geopolitical_report",
        "market_movers_report",
        "sector_performance_report",
        "industry_deep_dive_report",
        "macro_scan_summary",
    ]:
        content = result.get(key, "")
        if content:
            (save_dir / f"{key}.md").write_text(content)

    # Display the final watchlist
    summary = result.get("macro_scan_summary", "")
    if summary:
        console.print(Panel("[bold]Macro Scan Summary[/bold]", border_style="green"))
        console.print(Markdown(summary[:3000]))

        # Try to parse and show watchlist table
        try:
            summary_data = extract_json(summary)
            stocks = summary_data.get("stocks_to_investigate", [])
            if stocks:
                table = Table(title="Stocks to Investigate", box=box.ROUNDED)
                table.add_column("Ticker", style="cyan bold")
                table.add_column("Name")
                table.add_column("Sector")
                table.add_column("Conviction", style="green")
                table.add_column("Thesis")
                for s in stocks:
                    table.add_row(
                        s.get("ticker", ""),
                        s.get("name", ""),
                        s.get("sector", ""),
                        s.get("conviction", "").upper(),
                        s.get("thesis_angle", ""),
                    )
                console.print(table)
        except (json.JSONDecodeError, KeyError, ValueError):
            pass  # Summary wasn't valid JSON — already printed as markdown

    # Write observability log
    run_logger.write_log(save_dir / "run_log.jsonl")
    scan_summary = run_logger.summary()
    vendor_breakdown = format_vendor_breakdown(scan_summary)
    av_assessment = format_av_assessment(scan_summary)
    console.print(
        f"[dim]LLM calls: {scan_summary['llm_calls']} | "
        f"Tokens: {scan_summary['tokens_in']}→{scan_summary['tokens_out']} | "
        f"Tools: {scan_summary['tool_calls']} | "
        f"Vendor calls: {scan_summary['vendor_success']}ok/{scan_summary['vendor_fail']}fail[/dim]"
    )
    if vendor_breakdown:
        console.print(f"[dim]  Vendors: {vendor_breakdown}[/dim]")
    console.print(f"[dim]  {av_assessment}[/dim]")
    set_run_logger(None)

    # Append to daily digest and sync to NotebookLM
    scan_parts = []
    if result.get("geopolitical_report"):
        scan_parts.append(f"### Geopolitical & Macro\n{result['geopolitical_report']}")
    if result.get("market_movers_report"):
        scan_parts.append(f"### Market Movers\n{result['market_movers_report']}")
    if result.get("sector_performance_report"):
        scan_parts.append(
            f"### Sector Performance\n{result['sector_performance_report']}"
        )
    if result.get("industry_deep_dive_report"):
        scan_parts.append(
            f"### Industry Deep Dive\n{result['industry_deep_dive_report']}"
        )
    if result.get("macro_scan_summary"):
        scan_parts.append(f"### Macro Scan Summary\n{result['macro_scan_summary']}")

    macro_content = "\n\n".join(scan_parts)

    if macro_content:
        digest_path = append_to_digest(scan_date, "scan", "Market Scan", macro_content)
        sync_to_notebooklm(digest_path, scan_date)

    console.print(f"\n[green]Results saved to {save_dir}[/green]")


def run_pipeline(
    macro_path_str: Optional[str] = None,
    min_conviction_opt: Optional[str] = None,
    ticker_filter_list: Optional[list[str]] = None,
    analysis_date_opt: Optional[str] = None,
    dry_run_opt: Optional[bool] = None,
):
    """Full pipeline: scan -> filter -> per-ticker deep dive."""
    import asyncio
    from tradingagents.pipeline.macro_bridge import (
        parse_macro_output,
        filter_candidates,
        run_all_tickers,
        save_results,
    )

    console.print(
        Panel(
            "[bold green]Macro → TradingAgents Pipeline[/bold green]",
            border_style="green",
        )
    )

    if macro_path_str is None:
        macro_output = typer.prompt("Path to macro scan JSON")
    else:
        macro_output = macro_path_str

    macro_path = Path(macro_output)
    if not macro_path.exists():
        console.print(f"[red]File not found: {macro_path}[/red]")
        raise typer.Exit(1)

    if min_conviction_opt is None:
        min_conviction = typer.prompt(
            "Minimum conviction (high/medium/low)", default="medium"
        )
    else:
        min_conviction = min_conviction_opt

    if ticker_filter_list is None:
        tickers_input = typer.prompt(
            "Specific tickers (comma-separated, or blank for all)", default=""
        )
        ticker_filter = [
            t.strip() for t in tickers_input.split(",") if t.strip()
        ] or None
    else:
        ticker_filter = ticker_filter_list

    if analysis_date_opt is None:
        analysis_date = typer.prompt(
            "Analysis date", default=datetime.datetime.now().strftime("%Y-%m-%d")
        )
    else:
        analysis_date = analysis_date_opt

    if dry_run_opt is None:
        dry_run = typer.confirm("Dry run (no API calls)?", default=False)
    else:
        dry_run = dry_run_opt

    # Parse macro output
    macro_context, all_candidates = parse_macro_output(macro_path)
    candidates = filter_candidates(all_candidates, min_conviction, ticker_filter)

    console.print(
        f"\n[cyan]Candidates: {len(candidates)} of {len(all_candidates)} stocks passed filter[/cyan]"
    )

    table = Table(title="Selected Stocks", box=box.ROUNDED)
    table.add_column("Ticker", style="cyan bold")
    table.add_column("Conviction")
    table.add_column("Sector")
    table.add_column("Name")
    for c in candidates:
        table.add_row(c.ticker, c.conviction.upper(), c.sector, c.name)
    console.print(table)

    if dry_run:
        console.print("\n[yellow]Dry run — skipping TradingAgents analysis[/yellow]")
        return

    if not candidates:
        console.print("[yellow]No candidates passed the filter.[/yellow]")
        return

    config = DEFAULT_CONFIG.copy()
    output_dir = get_daily_dir(analysis_date)

    run_logger = RunLogger()
    set_run_logger(run_logger)

    console.print(
        f"\n[cyan]Running TradingAgents for {len(candidates)} tickers...[/cyan]"
    )
    try:
        with Live(
            Spinner("dots", text="Analyzing..."), console=console, transient=True
        ):
            results = asyncio.run(
                run_all_tickers(candidates, macro_context, config, analysis_date)
            )
    except Exception as e:
        console.print(f"[red]Pipeline failed: {e}[/red]")
        raise typer.Exit(1)

    save_results(results, macro_context, output_dir)

    # Write observability log
    output_dir.mkdir(parents=True, exist_ok=True)
    run_logger.write_log(output_dir / "run_log.jsonl")
    pipe_summary = run_logger.summary()
    vendor_breakdown = format_vendor_breakdown(pipe_summary)
    av_assessment = format_av_assessment(pipe_summary)
    console.print(
        f"[dim]LLM calls: {pipe_summary['llm_calls']} | "
        f"Tokens: {pipe_summary['tokens_in']}→{pipe_summary['tokens_out']} | "
        f"Tools: {pipe_summary['tool_calls']} | "
        f"Vendor calls: {pipe_summary['vendor_success']}ok/{pipe_summary['vendor_fail']}fail[/dim]"
    )
    if vendor_breakdown:
        console.print(f"[dim]  Vendors: {vendor_breakdown}[/dim]")
    console.print(f"[dim]  {av_assessment}[/dim]")
    set_run_logger(None)

    # Append to daily digest and sync to NotebookLM
    from tradingagents.pipeline.macro_bridge import render_combined_summary

    pipeline_summary = render_combined_summary(results, macro_context)
    digest_path = append_to_digest(
        analysis_date, "pipeline", "Pipeline Summary", pipeline_summary
    )
    sync_to_notebooklm(digest_path, analysis_date)

    successes = [r for r in results if not r.error]
    failures = [r for r in results if r.error]
    console.print(
        f"\n[green]Done: {len(successes)} succeeded, {len(failures)} failed[/green]"
    )
    console.print(f"Reports saved to: {output_dir.resolve()}")
    if failures:
        for r in failures:
            console.print(f"  [red]{r.ticker}: {r.error}[/red]")


@app.command()
def analyze():
    """Run per-ticker multi-agent analysis."""
    run_analysis()


@app.command()
def scan(
    date: Optional[str] = typer.Option(
        None, "--date", "-d", help="Scan date in YYYY-MM-DD format (default: today)"
    ),
):
    """Run 3-phase macro scanner (geopolitical → sector → synthesis)."""
    run_scan(date=date)


@app.command()
def pipeline():
    """Full pipeline: macro scan JSON → filter → per-ticker deep dive."""
    run_pipeline()


def run_portfolio(portfolio_id: str, date: str, macro_path: Path):
    """Run the Portfolio Manager end-to-end workflow."""
    import json
    import yfinance as yf
    from tradingagents.graph.portfolio_graph import PortfolioGraph
    from tradingagents.portfolio.repository import PortfolioRepository

    console.print(
        Panel(
            "[bold green]Portfolio Manager Execution[/bold green]", border_style="green"
        )
    )

    if not macro_path.exists():
        console.print(f"[red]Scan summary not found: {macro_path}[/red]")
        raise typer.Exit(1)

    with open(macro_path, "r") as f:
        try:
            scan_summary = json.load(f)
        except json.JSONDecodeError:
            console.print(f"[red]Failed to parse JSON at {macro_path}[/red]")
            raise typer.Exit(1)

    repo = PortfolioRepository()

    # Check if portfolio exists
    portfolio = repo.get_portfolio(portfolio_id)
    if not portfolio:
        console.print(
            f"[yellow]Portfolio '{portfolio_id}' not found. Please ensure it is created in the database.[/yellow]"
        )
        raise typer.Exit(1)

    holdings = repo.get_holdings(portfolio_id)

    candidates = scan_summary.get("stocks_to_investigate", [])
    holding_tickers = [h.ticker for h in holdings]

    all_tickers = set(candidates + holding_tickers)

    console.print(f"[cyan]Fetching prices for {len(all_tickers)} tickers...[/cyan]")
    prices = {}
    for ticker in all_tickers:
        try:
            prices[ticker] = float(yf.Ticker(ticker).fast_info["lastPrice"])
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not fetch price for {ticker}: {e}[/yellow]"
            )
            prices[ticker] = 0.0

    console.print(f"[cyan]Running PortfolioGraph for '{portfolio_id}'...[/cyan]")
    try:
        with Live(
            Spinner("dots", text="Managing portfolio..."),
            console=console,
            transient=True,
        ):
            graph = PortfolioGraph(debug=False, repo=repo)
            result = graph.run(
                portfolio_id=portfolio_id,
                date=date,
                prices=prices,
                scan_summary=scan_summary,
            )
    except Exception as e:
        console.print(f"[red]Portfolio execution failed: {e}[/red]")
        raise typer.Exit(1)

    console.print("[green]Portfolio execution completed successfully![/green]")
    if "pm_decision" in result:
        console.print(
            Panel(
                Markdown(str(result["pm_decision"])),
                title="PM Decision",
                border_style="blue",
            )
        )


@app.command()
def portfolio():
    """Run the Portfolio Manager Phase 6 workflow."""
    console.print(
        Panel("[bold green]Portfolio Manager CLI[/bold green]", border_style="green")
    )

    portfolio_id = typer.prompt("Portfolio ID", default="main_portfolio")
    date = typer.prompt(
        "Analysis date", default=datetime.datetime.now().strftime("%Y-%m-%d")
    )

    macro_output = typer.prompt("Path to macro scan JSON")
    macro_path = Path(macro_output)

    run_portfolio(portfolio_id, date, macro_path)


@app.command(name="check-portfolio")
def check_portfolio(
    portfolio_id: str = typer.Option(
        "main_portfolio", "--portfolio-id", "-p", help="Portfolio ID"
    ),
    date: Optional[str] = typer.Option(
        None, "--date", "-d", help="Analysis date in YYYY-MM-DD format (default: today)"
    ),
):
    """Run Portfolio Manager to review current holdings only (no new candidates)."""
    import json
    import tempfile

    console.print(
        Panel(
            "[bold green]Portfolio Manager: Holdings Review[/bold green]",
            border_style="green",
        )
    )
    if date is None:
        date = datetime.datetime.now().strftime("%Y-%m-%d")

    # Create a dummy scan_summary with no candidates
    dummy_scan = {"stocks_to_investigate": []}
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as f:
        json.dump(dummy_scan, f)
        dummy_path = Path(f.name)

    try:
        run_portfolio(portfolio_id, date, dummy_path)
    finally:
        dummy_path.unlink(missing_ok=True)


@app.command()
def auto(
    portfolio_id: str = typer.Option(
        "main_portfolio", "--portfolio-id", "-p", help="Portfolio ID"
    ),
    date: Optional[str] = typer.Option(
        None, "--date", "-d", help="Analysis date in YYYY-MM-DD format (default: today)"
    ),
):
    """Run end-to-end: scan -> pipeline -> portfolio manager."""
    console.print(
        Panel("[bold green]TradingAgents Auto Mode[/bold green]", border_style="green")
    )
    if date is None:
        date = datetime.datetime.now().strftime("%Y-%m-%d")

    console.print("\n[bold magenta]--- Step 1: Market Scan ---[/bold magenta]")
    run_scan(date=date)

    console.print("\n[bold magenta]--- Step 2: Per-Ticker Pipeline ---[/bold magenta]")
    macro_path = get_daily_dir(date) / "summary" / "scan_summary.json"
    run_pipeline(
        macro_path_str=str(macro_path),
        min_conviction_opt="medium",
        ticker_filter_list=None,
        analysis_date_opt=date,
        dry_run_opt=False,
    )

    console.print("\n[bold magenta]--- Step 3: Portfolio Manager ---[/bold magenta]")
    run_portfolio(portfolio_id, date, macro_path)


@app.command(name="estimate-api")
def estimate_api(
    command: str = typer.Argument("all", help="Command to estimate: analyze, scan, pipeline, or all"),
    num_tickers: int = typer.Option(5, "--tickers", "-t", help="Expected tickers for pipeline estimate"),
    num_indicators: int = typer.Option(6, "--indicators", "-i", help="Expected indicator calls per ticker"),
):
    """Estimate API usage per vendor (helps decide if AV premium is needed)."""
    from tradingagents.api_usage import (
        estimate_analyze,
        estimate_scan,
        estimate_pipeline,
        format_estimate,
        AV_FREE_DAILY_LIMIT,
        AV_PREMIUM_PER_MINUTE,
    )

    console.print(Panel("[bold green]API Usage Estimation[/bold green]", border_style="green"))
    console.print(
        f"[dim]Alpha Vantage tiers: FREE = {AV_FREE_DAILY_LIMIT} calls/day | "
        f"Premium ($30/mo) = {AV_PREMIUM_PER_MINUTE} calls/min, unlimited daily[/dim]\n"
    )

    estimates = []
    if command in ("analyze", "all"):
        estimates.append(estimate_analyze(num_indicators=num_indicators))
    if command in ("scan", "all"):
        estimates.append(estimate_scan())
    if command in ("pipeline", "all"):
        estimates.append(estimate_pipeline(num_tickers=num_tickers, num_indicators=num_indicators))

    if not estimates:
        console.print(f"[red]Unknown command: {command}. Use: analyze, scan, pipeline, or all[/red]")
        raise typer.Exit(1)

    for est in estimates:
        console.print(Panel(format_estimate(est), title=est.command, border_style="cyan"))

    # Overall AV assessment
    console.print("\n[bold]Alpha Vantage Subscription Recommendation:[/bold]")
    max_av = max(e.vendor_calls.alpha_vantage for e in estimates)
    if max_av == 0:
        console.print(
            "  [green]✓ Current config uses yfinance (free) for all data.[/green]\n"
            "  [green]  Alpha Vantage subscription is NOT needed.[/green]\n"
            "  [dim]  To switch to AV, set TRADINGAGENTS_VENDOR_* env vars to 'alpha_vantage'.[/dim]"
        )
    else:
        total_daily = sum(e.vendor_calls.alpha_vantage for e in estimates)
        if total_daily <= AV_FREE_DAILY_LIMIT:
            console.print(
                f"  [green]✓ Total AV calls ({total_daily}) fit the FREE tier ({AV_FREE_DAILY_LIMIT}/day).[/green]\n"
                f"  [green]  No premium subscription needed for a single daily run.[/green]"
            )
        else:
            console.print(
                f"  [yellow]⚠ Total AV calls ({total_daily}) exceed the FREE tier ({AV_FREE_DAILY_LIMIT}/day).[/yellow]\n"
                f"  [yellow]  Premium subscription recommended ($30/month).[/yellow]"
            )


if __name__ == "__main__":
    app()
