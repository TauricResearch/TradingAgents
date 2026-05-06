import datetime
import time
from collections import deque
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
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
from cli.stats_handler import StatsCallbackHandler
from cli.utils import (
    ask_anthropic_effort,
    ask_gemini_thinking_config,
    ask_openai_reasoning_effort,
    ask_output_language,
    default_backend_url_for_provider,
    normalize_ticker_symbol,
    parse_analysts_flag,
    parse_research_depth_flag,
    print_mlx_setup_reminder,
    select_analysts,
    select_deep_thinking_agent,
    select_llm_provider,
    select_research_depth,
    select_shallow_thinking_agent,
    validate_analysis_date_cli,
    verify_mlx_server_reachable,
    warn_mlx_quick_deep_mismatch,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import save_report_to_disk  # noqa: F401  (re-export for backcompat)

# Load environment variables
load_dotenv()
load_dotenv(".env.enterprise", override=False)

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

    def __init__(self, max_length=100):
        self.messages = deque(maxlen=max_length)
        self.tool_calls = deque(maxlen=max_length)
        self.current_report = None
        self.final_report = None  # Store the complete final report
        self.agent_status = {}
        self.current_agent = None
        self.report_sections = {}
        self.selected_analysts = []
        self._processed_message_ids = set()

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
            self.current_report = f"### {section_titles[latest_section]}\n{latest_content}"

        # Update the final complete report
        self._update_final_report()

    def _update_final_report(self):
        report_parts = []

        # Analyst Team Reports - use .get() to handle missing sections
        analyst_sections = ["market_report", "sentiment_report", "news_report", "fundamentals_report"]
        if any(self.report_sections.get(section) for section in analyst_sections):
            report_parts.append("## Analyst Team Reports")
            if self.report_sections.get("market_report"):
                report_parts.append(f"### Market Analysis\n{self.report_sections['market_report']}")
            if self.report_sections.get("sentiment_report"):
                report_parts.append(f"### Social Sentiment\n{self.report_sections['sentiment_report']}")
            if self.report_sections.get("news_report"):
                report_parts.append(f"### News Analysis\n{self.report_sections['news_report']}")
            if self.report_sections.get("fundamentals_report"):
                report_parts.append(f"### Fundamentals Analysis\n{self.report_sections['fundamentals_report']}")

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
    layout["main"].split_column(Layout(name="upper", ratio=3), Layout(name="analysis", ratio=5))
    layout["upper"].split_row(Layout(name="progress", ratio=2), Layout(name="messages", ratio=3))
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
        if status == "in_progress":
            spinner = Spinner("dots", text="[blue]in_progress[/blue]", style="bold cyan")
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
                spinner = Spinner("dots", text="[blue]in_progress[/blue]", style="bold cyan")
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

    layout["progress"].update(Panel(progress_table, title="Progress", border_style="cyan", padding=(1, 2)))

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
    messages_table.add_column("Content", style="white", no_wrap=False, ratio=1)  # Make content column expand

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
    agents_completed = sum(1 for status in message_buffer.agent_status.values() if status == "completed")
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


def get_user_selections():
    """Get all user selections before starting the analysis display."""
    # Display ASCII art welcome message
    with open(Path(__file__).parent / "static" / "welcome.txt", "r", encoding="utf-8") as f:
        welcome_ascii = f.read()

    # Create welcome box content
    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgents: Multi-Agents LLM Financial Trading Framework - CLI[/bold green]\n\n"
    welcome_content += "[bold]Workflow Steps:[/bold]\n"
    welcome_content += (
        "I. Analyst Team → II. Research Team → III. Trader → IV. Risk Management → V. Portfolio Management\n\n"
    )
    welcome_content += "[dim]Built by [Tauric Research](https://github.com/TauricResearch)[/dim]"

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
            "Step 1: Ticker Symbol",
            "Enter the exact ticker symbol to analyze, including exchange suffix when needed"
            " (examples: SPY, CNC.TO, 7203.T, 0700.HK)",
            "SPY",
        )
    )
    while True:
        selected_ticker = normalize_ticker_symbol(get_ticker())
        if confirm_resolved_ticker(selected_ticker):
            break

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

    # Step 3: Output language
    console.print(
        create_question_box("Step 3: Output Language", "Select the language for analyst reports and final decision")
    )
    output_language = ask_output_language()

    # Step 4: Select analysts
    console.print(create_question_box("Step 4: Analysts Team", "Select your LLM analyst agents for the analysis"))
    selected_analysts = select_analysts()
    console.print(f"[green]Selected analysts:[/green] {', '.join(analyst.value for analyst in selected_analysts)}")

    # Step 5: Research depth
    console.print(create_question_box("Step 5: Research Depth", "Select your research depth level"))
    selected_research_depth = select_research_depth()

    # Step 6: LLM Provider
    console.print(create_question_box("Step 6: LLM Provider", "Select your LLM provider"))
    selected_llm_provider, backend_url = select_llm_provider()
    if selected_llm_provider.lower() == "mlx":
        print_mlx_setup_reminder(backend_url)

    # Step 7: Thinking agents
    console.print(create_question_box("Step 7: Thinking Agents", "Select your thinking agents for analysis"))
    selected_shallow_thinker = select_shallow_thinking_agent(selected_llm_provider)
    selected_deep_thinker = select_deep_thinking_agent(selected_llm_provider)
    if selected_llm_provider.lower() == "mlx":
        warn_mlx_quick_deep_mismatch(selected_shallow_thinker, selected_deep_thinker)

    # Step 8: Provider-specific thinking configuration
    thinking_level = None
    reasoning_effort = None
    anthropic_effort = None
    claude_code_effort = None

    provider_lower = selected_llm_provider.lower()
    if provider_lower == "google":
        console.print(create_question_box("Step 8: Thinking Mode", "Configure Gemini thinking mode"))
        thinking_level = ask_gemini_thinking_config()
    elif provider_lower == "openai":
        console.print(create_question_box("Step 8: Reasoning Effort", "Configure OpenAI reasoning effort level"))
        reasoning_effort = ask_openai_reasoning_effort()
    elif provider_lower == "anthropic":
        console.print(create_question_box("Step 8: Effort Level", "Configure Claude effort level"))
        anthropic_effort = ask_anthropic_effort()
    elif provider_lower == "claude_code":
        console.print(
            create_question_box(
                "Step 8: Effort Level",
                "Configure Claude Code effort level"
            )
        )
        claude_code_effort = ask_claude_code_effort()

    if provider_lower == "mlx":
        verify_mlx_server_reachable(backend_url)

    return {
        "ticker": selected_ticker,
        "analysis_date": analysis_date,
        "analysts": selected_analysts,
        "research_depth": selected_research_depth,
        "llm_provider": selected_llm_provider.lower(),
        "backend_url": backend_url,
        "shallow_thinker": selected_shallow_thinker,
        "deep_thinker": selected_deep_thinker,
        "google_thinking_level": thinking_level,
        "openai_reasoning_effort": reasoning_effort,
        "anthropic_effort": anthropic_effort,
        "claude_code_effort": claude_code_effort,
        "output_language": output_language,
    }


def get_ticker():
    """Get ticker symbol from user input."""
    return typer.prompt("", default="SPY")


def confirm_resolved_ticker(ticker: str) -> bool:
    """Show the company resolved from yfinance for `ticker` and ask the user to
    confirm it. Returns True to proceed, False to re-prompt for the ticker.

    Catches the common case where a model would otherwise hallucinate a wrong
    company for an exchange-suffixed ticker (e.g. NPN.JO → Nornickel/Oslo
    instead of Naspers/JSE).
    """
    from tradingagents.dataflows.y_finance import get_instrument_metadata

    with console.status(f"[cyan]Looking up {ticker}...[/cyan]", spinner="dots"):
        metadata = get_instrument_metadata(ticker)

    if not metadata:
        console.print(
            Panel(
                f"[yellow]Could not resolve company info for[/yellow] [bold]{ticker}[/bold]"
                "\n[dim]The ticker may be invalid, delisted, or unavailable on yfinance."
                " You can still proceed, but the analysis may be inaccurate.[/dim]",
                title="Ticker not verified",
                border_style="yellow",
                padding=(1, 2),
            )
        )
        return typer.confirm("Continue with this ticker anyway?", default=False)

    name = metadata.get("name") or "(unknown company)"
    exchange = metadata.get("exchange") or "(unknown exchange)"
    currency = metadata.get("currency") or "(unknown currency)"
    quote_type = metadata.get("quote_type") or "(unknown type)"

    console.print(
        Panel(
            f"[bold]Ticker:[/bold] {ticker}\n"
            f"[bold]Company:[/bold] {name}\n"
            f"[bold]Exchange:[/bold] {exchange}\n"
            f"[bold]Currency:[/bold] {currency}\n"
            f"[bold]Type:[/bold] {quote_type}",
            title="Resolved instrument",
            border_style="green",
            padding=(1, 2),
        )
    )
    return typer.confirm("Proceed with this company?", default=True)


def print_resolved_ticker_summary(ticker: str) -> None:
    """Non-interactive counterpart to `confirm_resolved_ticker`: print the
    resolved instrument so users running with --yes still see what's being
    analyzed, without gating progress behind a prompt."""
    from tradingagents.dataflows.y_finance import get_instrument_metadata

    with console.status(f"[cyan]Looking up {ticker}...[/cyan]", spinner="dots"):
        metadata = get_instrument_metadata(ticker)

    if not metadata:
        console.print(f"[yellow]Could not resolve company info for {ticker}; proceeding anyway.[/yellow]")
        return

    name = metadata.get("name") or "(unknown company)"
    exchange = metadata.get("exchange") or "(unknown exchange)"
    currency = metadata.get("currency") or ""
    suffix = f" ({currency})" if currency else ""
    console.print(f"[green]Analyzing[/green] [bold]{ticker}[/bold] — {name} on {exchange}{suffix}")


def get_analysis_date():
    """Get the analysis date from user input."""
    while True:
        date_str = typer.prompt("", default=datetime.datetime.now().strftime("%Y-%m-%d"))
        try:
            # Validate date format and ensure it's not in the future
            analysis_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            if analysis_date.date() > datetime.datetime.now().date():
                console.print("[red]Error: Analysis date cannot be in the future[/red]")
                continue
            return date_str
        except ValueError:
            console.print("[red]Error: Invalid date format. Please use YYYY-MM-DD[/red]")


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
            console.print(Panel("[bold]IV. Risk Management Team Decision[/bold]", border_style="red"))
            for title, content in risk_reports:
                console.print(Panel(Markdown(content), title=title, border_style="blue", padding=(1, 2)))

        # V. Portfolio Manager Decision
        if risk.get("judge_decision"):
            console.print(Panel("[bold]V. Portfolio Manager Decision[/bold]", border_style="green"))
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


def format_tool_args(args, max_length=80) -> str:
    """Format tool arguments for terminal display."""
    result = str(args)
    if len(result) > max_length:
        return result[: max_length - 3] + "..."
    return result


def build_cli_selections(
    *,
    ticker: str,
    analysis_date: str,
    output_language: str,
    analysts_csv: str,
    research_depth: str,
    llm_provider: str,
    backend_url: Optional[str],
    quick_model: Optional[str],
    deep_model: Optional[str],
    model: Optional[str],
    google_thinking_level: Optional[str],
    openai_reasoning_effort: Optional[str],
    anthropic_effort: Optional[str],
) -> dict:
    """Assemble the selections dict used by ``run_analysis`` from CLI flags."""
    try:
        depth_val = parse_research_depth_flag(research_depth)
        analysts_list = parse_analysts_flag(analysts_csv)
        date_ok = validate_analysis_date_cli(analysis_date)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e

    prov = llm_provider.strip().lower()
    if model:
        qm = dm = model.strip()
    else:
        if not quick_model or not deep_model:
            console.print("[red]Provide --model, or both --quick-model and --deep-model.[/red]")
            raise typer.Exit(1)
        qm = quick_model.strip()
        dm = deep_model.strip()

    backend = backend_url.strip() if backend_url and backend_url.strip() else default_backend_url_for_provider(prov)

    g_think = None
    o_effort = None
    a_effort = None
    if prov == "google":
        g = (google_thinking_level or "high").strip().lower()
        if g not in ("high", "minimal"):
            console.print("[red]--google-thinking must be 'high' or 'minimal'.[/red]")
            raise typer.Exit(1)
        g_think = g
    elif prov == "openai":
        o = (openai_reasoning_effort or "medium").strip().lower()
        if o not in ("low", "medium", "high"):
            console.print("[red]--openai-reasoning must be 'low', 'medium', or 'high'.[/red]")
            raise typer.Exit(1)
        o_effort = o
    elif prov == "anthropic":
        a = (anthropic_effort or "high").strip().lower()
        if a not in ("low", "medium", "high"):
            console.print("[red]--anthropic-effort must be 'low', 'medium', or 'high'.[/red]")
            raise typer.Exit(1)
        a_effort = a

    if prov == "mlx":
        warn_mlx_quick_deep_mismatch(qm, dm)
        verify_mlx_server_reachable(backend)

    normalized_ticker = normalize_ticker_symbol(ticker)
    print_resolved_ticker_summary(normalized_ticker)

    return {
        "ticker": normalized_ticker,
        "analysis_date": date_ok,
        "analysts": analysts_list,
        "research_depth": depth_val,
        "llm_provider": prov,
        "backend_url": backend,
        "shallow_thinker": qm,
        "deep_thinker": dm,
        "google_thinking_level": g_think,
        "openai_reasoning_effort": o_effort,
        "anthropic_effort": a_effort,
        "output_language": (output_language or "English").strip(),
    }


def run_analysis(
    checkpoint: bool = False,
    selections: Optional[dict] = None,
    non_interactive: bool = False,
):
    if selections is None:
        selections = get_user_selections()

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
    config["claude_code_effort"] = selections.get("claude_code_effort")
    config["output_language"] = selections.get("output_language", "English")
    config["checkpoint_enabled"] = checkpoint

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

    # Initialize message buffer with selected analysts
    message_buffer.init_for_analysis(selected_analyst_keys)

    # Track start time for elapsed display
    start_time = time.time()

    # Note: previously the CLI also streamed per-section markdown and a
    # message_tool.log into <results_dir>/<TICKER>/<DATE>/. That layout was
    # duplicative — every run now produces exactly one canonical folder
    # under TradingAgentsGraph._run_graph (see tradingagents/reporting.py).

    # Now start the display layout
    layout = create_layout()

    with Live(layout, refresh_per_second=4):
        # Initial display
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # Add initial messages
        message_buffer.add_message("System", f"Selected ticker: {selections['ticker']}")
        message_buffer.add_message("System", f"Analysis date: {selections['analysis_date']}")
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
        spinner_text = f"Analyzing {selections['ticker']} on {selections['analysis_date']}..."
        update_display(layout, spinner_text, stats_handler=stats_handler, start_time=start_time)

        # Initialize state and get graph args with callbacks
        init_agent_state = graph.propagator.create_initial_state(selections["ticker"], selections["analysis_date"])
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
                    message_buffer.update_report_section("investment_plan", f"### Research Manager Decision\n{judge}")
                    update_research_team_status("completed")
                    message_buffer.update_agent_status("Trader", "in_progress")

            # Trading Team
            if chunk.get("trader_investment_plan"):
                message_buffer.update_report_section("trader_investment_plan", chunk["trader_investment_plan"])
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
            update_display(layout, stats_handler=stats_handler, start_time=start_time)

            trace.append(chunk)

        final_state = trace[-1]

        # Update all agent statuses to completed
        for agent in message_buffer.agent_status:
            message_buffer.update_agent_status(agent, "completed")

        message_buffer.add_message("System", f"Completed analysis for {selections['analysis_date']}")

        # Update final report sections
        for section in message_buffer.report_sections.keys():
            if section in final_state:
                message_buffer.update_report_section(section, final_state[section])

        update_display(layout, stats_handler=stats_handler, start_time=start_time)

    if non_interactive:
        rdir = Path(config["results_dir"]) / selections["ticker"] / selections["analysis_date"]
        console.print(f"\n[bold cyan]Analysis complete.[/bold cyan] Artifacts: [dim]{rdir.resolve()}[/dim]")
        return

    # Post-analysis prompts (outside Live context for clean interaction)
    console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")
    # Report folder is already written by TradingAgentsGraph._run_graph in the
    # canonical structured layout under config["results_dir"].
    console.print(
        f"[green]✓ Report saved under:[/green] {Path(config['results_dir']).resolve()}/"
        f"{selections['ticker']}_<DATE>_<TIMESTAMP>/"
    )

    # Prompt to display full report
    display_choice = typer.prompt("\nDisplay full report on screen?", default="Y").strip().upper()
    if display_choice in ("Y", "YES", ""):
        display_complete_report(final_state)


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
    non_interactive: bool = typer.Option(
        False,
        "--yes",
        "-y",
        "--non-interactive",
        help=(
            "Skip the wizard; requires --ticker, --date, --analysts, --depth, "
            "--provider, and --model (or --quick-model + --deep-model)."
        ),
    ),
    ticker: Optional[str] = typer.Option(
        None,
        "--ticker",
        "-t",
        help="Symbol to analyze (e.g. SPY, 7203.T).",
    ),
    analysis_date: Optional[str] = typer.Option(
        None,
        "--date",
        "-d",
        help="Analysis date YYYY-MM-DD.",
    ),
    output_language: Optional[str] = typer.Option(
        None,
        "--output-language",
        "--lang",
        help="Report language (default: English).",
    ),
    analysts: Optional[str] = typer.Option(
        None,
        "--analysts",
        "-a",
        help="Comma-separated: market,social,news,fundamentals.",
    ),
    research_depth: Optional[str] = typer.Option(
        None,
        "--depth",
        help="shallow|medium|deep or 1|3|5.",
    ),
    llm_provider: Optional[str] = typer.Option(
        None,
        "--provider",
        "-p",
        help="LLM provider key (openai, google, mlx, ollama, ...).",
    ),
    backend_url: Optional[str] = typer.Option(
        None,
        "--backend-url",
        help="Override API base URL (default per provider if omitted).",
    ),
    quick_model: Optional[str] = typer.Option(
        None,
        "--quick-model",
        help="Quick-thinking model / deployment name.",
    ),
    deep_model: Optional[str] = typer.Option(
        None,
        "--deep-model",
        help="Deep-thinking model / deployment name.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Use the same model for quick and deep thinking.",
    ),
    google_thinking_level: Optional[str] = typer.Option(
        None,
        "--google-thinking",
        help="Gemini thinking: high or minimal (default: high).",
    ),
    openai_reasoning_effort: Optional[str] = typer.Option(
        None,
        "--openai-reasoning",
        help="OpenAI reasoning effort: low, medium, high (default: medium).",
    ),
    anthropic_effort: Optional[str] = typer.Option(
        None,
        "--anthropic-effort",
        help="Claude effort: low, medium, high (default: high).",
    ),
):
    analysis_flags = (
        ticker,
        analysis_date,
        output_language,
        analysts,
        research_depth,
        llm_provider,
        backend_url,
        quick_model,
        deep_model,
        model,
        google_thinking_level,
        openai_reasoning_effort,
        anthropic_effort,
    )
    if not non_interactive and any(f is not None for f in analysis_flags):
        console.print(
            "[yellow]CLI analysis flags require --yes / -y (--non-interactive); "
            "without it the wizard runs and flags are ignored.[/yellow]"
        )

    if clear_checkpoints:
        from tradingagents.graph.checkpointer import clear_all_checkpoints

        n = clear_all_checkpoints(DEFAULT_CONFIG["data_cache_dir"])
        console.print(f"[yellow]Cleared {n} checkpoint(s).[/yellow]")

    cli_selections: Optional[dict] = None
    if non_interactive:
        missing: list[str] = []
        if not ticker:
            missing.append("--ticker")
        if not analysis_date:
            missing.append("--date")
        if not analysts:
            missing.append("--analysts")
        if not research_depth:
            missing.append("--depth")
        if not llm_provider:
            missing.append("--provider")
        if not model and (not quick_model or not deep_model):
            missing.append("--model (or --quick-model and --deep-model)")
        if missing:
            console.print("[red]Non-interactive mode requires: " + ", ".join(missing) + "[/red]")
            raise typer.Exit(1)
        cli_selections = build_cli_selections(
            ticker=ticker,
            analysis_date=analysis_date,
            output_language=output_language or "English",
            analysts_csv=analysts,
            research_depth=research_depth,
            llm_provider=llm_provider,
            backend_url=backend_url,
            quick_model=quick_model,
            deep_model=deep_model,
            model=model,
            google_thinking_level=google_thinking_level,
            openai_reasoning_effort=openai_reasoning_effort,
            anthropic_effort=anthropic_effort,
        )

    run_analysis(
        checkpoint=checkpoint,
        selections=cli_selections,
        non_interactive=non_interactive,
    )


if __name__ == "__main__":
    app()
