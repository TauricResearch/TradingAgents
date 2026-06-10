from typing import Optional
import os
import datetime
import json
import typer
import questionary
from pathlib import Path
from functools import wraps
from rich.console import Console
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live
from rich.columns import Columns
from rich.markdown import Markdown
from rich.layout import Layout
from rich.text import Text
from rich.table import Table
from collections import deque
import time
from rich.tree import Tree
from rich import box
from rich.align import Align
from rich.rule import Rule

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.graph.analyst_execution import (
    INDIA_DEFAULT_ANALYSTS,
    AnalystWallTimeTracker,
    build_analyst_execution_plan,
    get_initial_analyst_node,
    sync_analyst_tracker_from_chunk,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.india.calendar import IndiaCalendarError, resolve_india_analysis_date
from tradingagents.dataflows.india.symbols import (
    IndiaSymbolError,
    safe_india_ticker_component,
    validate_india_symbol_or_raise,
)
from tradingagents.agents.analysts.india_compliance_risk_analyst import (
    INDIA_COMPLIANCE_DISCLAIMER,
)
from cli.models import AnalystType
from cli.utils import *
from cli.announcements import fetch_announcements, display_announcements
from cli.stats_handler import StatsCallbackHandler

console = Console()

app = typer.Typer(
    name="IndiaMarketAgents",
    help="IndiaMarketAgents CLI: India-only institutional market research copilot",
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
        "india_market": "India Market Technical Analyst",
        "india_fundamentals": "India Fundamentals Analyst",
        "india_news_filings": "India News & Filings Analyst",
        "india_macro_policy": "India Macro & Policy Analyst",
        "india_flows": "India Flows & Positioning Analyst",
        "india_sentiment": "India Sentiment Analyst",
        "india_compliance": "India Compliance & Risk Guard",
    }

    # Report section mapping: section -> (analyst_key for filtering, finalizing_agent)
    # analyst_key: which analyst selection controls this section (None = always included)
    # finalizing_agent: which agent must be "completed" for this report to count as done
    REPORT_SECTIONS = {
        "market_report": ("market", "Market Analyst"),
        "sentiment_report": ("social", "Sentiment Analyst"),
        "news_report": ("news", "News Analyst"),
        "fundamentals_report": ("fundamentals", "Fundamentals Analyst"),
        "india_market_report": ("india_market", "India Market Technical Analyst"),
        "india_fundamentals_report": ("india_fundamentals", "India Fundamentals Analyst"),
        "india_news_filings_report": ("india_news_filings", "India News & Filings Analyst"),
        "india_macro_policy_report": ("india_macro_policy", "India Macro & Policy Analyst"),
        "india_flows_report": ("india_flows", "India Flows & Positioning Analyst"),
        "india_sentiment_report": ("india_sentiment", "India Sentiment Analyst"),
        "india_compliance_report": ("india_compliance", "India Compliance & Risk Guard"),
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
                "india_market_report": "India Market Technical",
                "india_fundamentals_report": "India Fundamentals",
                "india_news_filings_report": "India News & Filings",
                "india_macro_policy_report": "India Macro & Policy",
                "india_flows_report": "India Flows & Positioning",
                "india_sentiment_report": "India Sentiment",
                "india_compliance_report": "India Compliance",
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
            "india_market_report",
            "india_fundamentals_report",
            "india_news_filings_report",
            "india_macro_policy_report",
            "india_flows_report",
            "india_sentiment_report",
            "india_compliance_report",
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
            india_titles = {
                "india_market_report": "India Market Technical",
                "india_fundamentals_report": "India Fundamentals",
                "india_news_filings_report": "India News & Filings",
                "india_macro_policy_report": "India Macro & Policy",
                "india_flows_report": "India Flows & Positioning",
                "india_sentiment_report": "India Sentiment",
                "india_compliance_report": "India Compliance",
            }
            for section, title in india_titles.items():
                if self.report_sections.get(section):
                    report_parts.append(f"### {title}\n{self.report_sections[section]}")

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
        return f"{n/1000:.1f}k"
    return str(n)


def update_display(layout, spinner_text=None, stats_handler=None, start_time=None):
    # Header with welcome message
    layout["header"].update(
        Panel(
            "[bold green]Welcome to IndiaMarketAgents CLI[/bold green]\n"
            "[dim]India-focused fork of TauricResearch/TradingAgents under Apache 2.0[/dim]",
            title="Welcome to IndiaMarketAgents",
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
            "India Market Technical Analyst",
            "India Fundamentals Analyst",
            "India News & Filings Analyst",
            "India Macro & Policy Analyst",
            "India Flows & Positioning Analyst",
            "India Sentiment Analyst",
            "India Compliance & Risk Guard",
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


def get_user_selections():
    """Get all user selections before starting the analysis display."""
    # Display ASCII art welcome message
    welcome_file = "india_welcome.txt" if DEFAULT_CONFIG.get("market_scope") == "india" else "welcome.txt"
    with open(Path(__file__).parent / "static" / welcome_file, "r", encoding="utf-8") as f:
        welcome_ascii = f.read()

    # Create welcome box content
    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]IndiaMarketAgents: India-only institutional market research copilot[/bold green]\n\n"
    welcome_content += "[bold]Workflow Steps:[/bold]\n"
    welcome_content += "I. India Analysts → II. Research Debate → III. Research View → IV. Risk Review → V. Portfolio Decision\n\n"
    welcome_content += f"[yellow]{INDIA_COMPLIANCE_DISCLAIMER}[/yellow]\n\n"
    welcome_content += (
        "[dim]Built as an India-focused fork of TauricResearch/TradingAgents under Apache 2.0.[/dim]"
    )

    # Create and center the welcome box
    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="Welcome to IndiaMarketAgents",
        subtitle="India-only research and education tooling",
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
            "Enter an NSE/BSE ticker. Use .NS for NSE and .BO for BSE (e.g. RELIANCE.NS).",
            "RELIANCE.NS",
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
    analysis_date = get_analysis_date()

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

    # Step 5: Research depth
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
        backend_url = DEFAULT_CONFIG["backend_url"] or provider_default_url(selected_llm_provider)
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
        selected_shallow_thinker = select_shallow_thinking_agent(selected_llm_provider)
        selected_deep_thinker = select_deep_thinking_agent(selected_llm_provider)

    # Step 8: Provider-specific thinking configuration
    thinking_level = None
    reasoning_effort = None
    anthropic_effort = None

    provider_lower = selected_llm_provider.lower()
    # When the provider is configured via environment we keep the run fully
    # non-interactive and use the config defaults (None = each provider's own
    # default reasoning/thinking behavior) instead of prompting.
    if provider_from_env:
        thinking_level = DEFAULT_CONFIG["google_thinking_level"]
        reasoning_effort = DEFAULT_CONFIG["openai_reasoning_effort"]
        anthropic_effort = DEFAULT_CONFIG["anthropic_effort"]
    elif provider_lower == "google":
        console.print(
            create_question_box(
                "Step 8: Thinking Mode",
                "Configure Gemini thinking mode"
            )
        )
        thinking_level = ask_gemini_thinking_config()
    elif provider_lower == "openai":
        console.print(
            create_question_box(
                "Step 8: Reasoning Effort",
                "Configure OpenAI reasoning effort level"
            )
        )
        reasoning_effort = ask_openai_reasoning_effort()
    elif provider_lower == "anthropic":
        console.print(
            create_question_box(
                "Step 8: Effort Level",
                "Configure Claude effort level"
            )
        )
        anthropic_effort = ask_anthropic_effort()

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
        "google_thinking_level": thinking_level,
        "openai_reasoning_effort": reasoning_effort,
        "anthropic_effort": anthropic_effort,
        "output_language": output_language,
    }


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
            if DEFAULT_CONFIG.get("market_scope") == "india":
                try:
                    resolved, warnings = resolve_india_analysis_date(date_str)
                except IndiaCalendarError as exc:
                    console.print(f"[red]Error: {exc}[/red]")
                    continue
                for warning in warnings:
                    console.print(f"[yellow]{warning}[/yellow]")
                return resolved
            return date_str
        except ValueError:
            console.print(
                "[red]Error: Invalid date format. Please use YYYY-MM-DD[/red]"
            )


SOURCE_COVERAGE_MARKERS = (
    "source:",
    "sources:",
    "source coverage",
    "data source",
    "user-supplied",
    "local filing",
    "company filing",
    "nse",
    "bse",
    "yahoo finance",
    "yfinance",
)
DATA_QUALITY_MARKERS = (
    "data quality",
    "data-quality",
    "coverage:",
    "confidence:",
    "limitation",
    "warning",
    "unavailable",
    "low-confidence",
)
CONFIDENCE_MARKERS = (
    "confidence:",
    "confidence",
    "low-confidence",
    "high-confidence",
)


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _contains_any_marker(content: str, markers: tuple[str, ...]) -> bool:
    lowered = content.lower()
    return any(marker in lowered for marker in markers)


def _build_report_section_record(
    filename: str,
    title: str,
    content: str,
    produced: bool,
) -> dict:
    source_detected = _contains_any_marker(content, SOURCE_COVERAGE_MARKERS)
    data_quality_detected = _contains_any_marker(content, DATA_QUALITY_MARKERS)
    confidence_detected = _contains_any_marker(content, CONFIDENCE_MARKERS)
    unavailable_detected = "unavailable" in content.lower()
    warnings = []
    if not produced:
        warnings.append("Section was not produced in the current run.")
    if not source_detected:
        warnings.append("Section text does not include explicit source coverage.")
    if not data_quality_detected:
        warnings.append("Section text does not include explicit data-quality coverage.")
    if not confidence_detected:
        warnings.append("Section text does not include explicit confidence coverage.")

    return {
        "title": title,
        "file": filename,
        "status": "available" if produced else "unavailable",
        "source_coverage_detected": source_detected,
        "data_quality_detected": data_quality_detected,
        "confidence_detected": confidence_detected,
        "contains_unavailable_marker": unavailable_detected,
        "warnings": warnings,
    }


def _format_report_quality_table(records: list[dict]) -> str:
    rows = [
        "| Section | File | Status | Source coverage | Data quality | Confidence | UNAVAILABLE marker |",
        "|---|---|---|---|---|---|---|",
    ]
    for record in records:
        rows.append(
            "| {title} | {file} | {status} | {source} | {quality} | {confidence} | {unavailable} |".format(
                title=record["title"],
                file=record["file"],
                status=record["status"],
                source=_yes_no(record["source_coverage_detected"]),
                quality=_yes_no(record["data_quality_detected"]),
                confidence=_yes_no(record["confidence_detected"]),
                unavailable=_yes_no(record["contains_unavailable_marker"]),
            )
        )
    return "\n".join(rows)


def _format_report_artifact_notes(record: dict) -> str:
    warnings = record["warnings"] or ["No writer-level coverage gaps detected."]
    warning_lines = "\n".join(f"- {warning}" for warning in warnings)
    return "\n".join(
        [
            "## Report Artifact Notes",
            "",
            f"- Section status: {record['status']}",
            f"- Source coverage detected in section text: {_yes_no(record['source_coverage_detected'])}",
            f"- Data-quality coverage detected in section text: {_yes_no(record['data_quality_detected'])}",
            f"- Confidence coverage detected in section text: {_yes_no(record['confidence_detected'])}",
            f"- UNAVAILABLE marker present: {_yes_no(record['contains_unavailable_marker'])}",
            "- Limitation: these are writer-level coverage checks only; they do not verify facts or fill missing data.",
            "",
            "### Coverage Warnings",
            "",
            warning_lines,
        ]
    )


def _format_sources_markdown(records: list[dict]) -> str:
    lines = [
        "# Sources And Data Quality Coverage",
        "",
        "This artifact is a report-writer coverage index. It does not certify data accuracy, replace official NSE/BSE/company filings, or fill missing data.",
        "",
        _format_report_quality_table(records),
        "",
        "## Coverage Warnings",
        "",
    ]
    for record in records:
        if record["warnings"]:
            lines.append(f"### {record['title']}")
            lines.extend(f"- {warning}" for warning in record["warnings"])
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_report_to_disk(final_state, ticker: str, save_path: Path):
    """Save complete analysis report to disk with organized IndiaMarketAgents files."""
    safe_ticker = safe_india_ticker_component(ticker) if DEFAULT_CONFIG.get("market_scope") == "india" else ticker
    save_path.mkdir(parents=True, exist_ok=True)
    sections = [
        f"# IndiaMarketAgents Research Report: {safe_ticker}",
        "",
        f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"Ticker/company: {safe_ticker}",
        f"Date: {final_state.get('trade_date', 'unknown')}",
        "",
        "## Compliance Disclaimer",
        INDIA_COMPLIANCE_DISCLAIMER,
        "",
        "## Data Quality And Source Coverage",
        "The table below is generated by the report writer from section text markers. It does not verify facts or infer missing data.",
    ]

    file_map = [
        ("1_market_technical.md", "India Market Technical", final_state.get("india_market_report") or final_state.get("market_report")),
        ("2_fundamentals.md", "India Fundamentals", final_state.get("india_fundamentals_report") or final_state.get("fundamentals_report")),
        ("3_news_filings.md", "India News & Filings", final_state.get("india_news_filings_report") or final_state.get("news_report")),
        ("4_macro_policy.md", "India Macro & Policy", final_state.get("india_macro_policy_report")),
        ("5_flows_positioning.md", "India Flows & Positioning", final_state.get("india_flows_report")),
        ("6_sentiment.md", "India Sentiment", final_state.get("india_sentiment_report") or final_state.get("sentiment_report")),
        ("7_research_debate.md", "Research Debate", None),
        ("trader_research_view.md", "Trader Research View", final_state.get("trader_investment_plan")),
        ("8_risk.md", "Risk Review", None),
        ("9_portfolio_decision.md", "Portfolio Research View", final_state.get("final_trade_decision")),
        ("compliance.md", "Compliance Guard", final_state.get("india_compliance_report")),
    ]

    debate = final_state.get("investment_debate_state") or {}
    research_debate = "\n\n".join(
        part
        for part in (
            f"### Bull Researcher\n{debate.get('bull_history', '')}" if debate.get("bull_history") else "",
            f"### Bear Researcher\n{debate.get('bear_history', '')}" if debate.get("bear_history") else "",
            f"### Research Manager\n{debate.get('judge_decision', '')}" if debate.get("judge_decision") else "",
        )
        if part
    )
    risk = final_state.get("risk_debate_state") or {}
    risk_review = "\n\n".join(
        part
        for part in (
            f"### Aggressive Risk Analyst\n{risk.get('aggressive_history', '')}" if risk.get("aggressive_history") else "",
            f"### Conservative Risk Analyst\n{risk.get('conservative_history', '')}" if risk.get("conservative_history") else "",
            f"### Neutral Risk Analyst\n{risk.get('neutral_history', '')}" if risk.get("neutral_history") else "",
        )
        if part
    )

    resolved_file_map = []
    section_records = []
    for filename, title, content in file_map:
        if filename == "7_research_debate.md":
            content = research_debate
        elif filename == "8_risk.md":
            content = risk_review
        produced = bool(content)
        if not content:
            content = "UNAVAILABLE: This section was not produced in the current run."
        record = _build_report_section_record(filename, title, content, produced)
        artifact_notes = _format_report_artifact_notes(record)
        text = (
            f"# {title}\n\n"
            f"## Compliance Disclaimer\n\n{INDIA_COMPLIANCE_DISCLAIMER}\n\n"
            f"## Report Section\n\n{content}\n\n"
            f"{artifact_notes}\n"
        )
        (save_path / filename).write_text(text, encoding="utf-8")
        resolved_file_map.append((title, content))
        section_records.append(record)

    sections.append(_format_report_quality_table(section_records))
    for title, content in resolved_file_map:
        sections.extend(["", f"## {title}", content])

    data_quality = {
        "symbol": safe_ticker,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "market_scope": DEFAULT_CONFIG.get("market_scope"),
        "disclaimer_present": True,
        "coverage_method": "writer_marker_detection_only",
        "limitations": [
            "Coverage flags are based on section text markers only.",
            "The report writer does not verify facts, source freshness, or numerical accuracy.",
            "Missing data must remain explicit as UNAVAILABLE or low-confidence in generated reports.",
        ],
        "sections": {record["title"]: record for record in section_records},
    }
    (save_path / "summary.json").write_text(
        json.dumps(
            {
                "symbol": safe_ticker,
                "date": final_state.get("trade_date"),
                "sections": [t for t, _ in resolved_file_map],
                "section_files": {record["title"]: record["file"] for record in section_records},
                "disclaimer_file": "disclaimer.md",
                "sources_file": "sources.md",
                "data_quality_file": "data_quality.json",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (save_path / "data_quality.json").write_text(json.dumps(data_quality, indent=2), encoding="utf-8")
    (save_path / "sources.md").write_text(_format_sources_markdown(section_records), encoding="utf-8")
    (save_path / "disclaimer.md").write_text(f"# Disclaimer\n\n{INDIA_COMPLIANCE_DISCLAIMER}\n", encoding="utf-8")
    (save_path / "complete_report.md").write_text("\n".join(sections) + "\n", encoding="utf-8")
    return save_path / "complete_report.md"


def display_complete_report(final_state):
    """Display the complete analysis report sequentially (avoids truncation)."""
    console.print()
    console.print(Rule("IndiaMarketAgents Complete Research Report", style="bold green"))
    console.print(Panel(INDIA_COMPLIANCE_DISCLAIMER, title="Compliance Disclaimer", border_style="yellow"))

    # I. Analyst Team Reports
    analysts = []
    if final_state.get("market_report") and not final_state.get("india_market_report"):
        analysts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report") and not final_state.get("india_sentiment_report"):
        analysts.append(("Sentiment Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report") and not final_state.get("india_news_filings_report"):
        analysts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report") and not final_state.get("india_fundamentals_report"):
        analysts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
    india_sections = [
        ("India Market Technical", final_state.get("india_market_report")),
        ("India Fundamentals", final_state.get("india_fundamentals_report")),
        ("India News & Filings", final_state.get("india_news_filings_report")),
        ("India Macro & Policy", final_state.get("india_macro_policy_report")),
        ("India Flows & Positioning", final_state.get("india_flows_report")),
        ("India Sentiment", final_state.get("india_sentiment_report")),
        ("India Compliance", final_state.get("india_compliance_report")),
    ]
    analysts.extend((title, content) for title, content in india_sections if content)
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
ANALYST_ORDER = [
    "market",
    "social",
    "news",
    "fundamentals",
    "india_market",
    "india_fundamentals",
    "india_news_filings",
    "india_macro_policy",
    "india_flows",
    "india_sentiment",
    "india_compliance",
]
ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
    "india_market": "India Market Technical Analyst",
    "india_fundamentals": "India Fundamentals Analyst",
    "india_news_filings": "India News & Filings Analyst",
    "india_macro_policy": "India Macro & Policy Analyst",
    "india_flows": "India Flows & Positioning Analyst",
    "india_sentiment": "India Sentiment Analyst",
    "india_compliance": "India Compliance & Risk Guard",
}
ANALYST_REPORT_MAP = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
    "india_market": "india_market_report",
    "india_fundamentals": "india_fundamentals_report",
    "india_news_filings": "india_news_filings_report",
    "india_macro_policy": "india_macro_policy_report",
    "india_flows": "india_flows_report",
    "india_sentiment": "india_sentiment_report",
    "india_compliance": "india_compliance_report",
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

def run_analysis(checkpoint: bool = False):
    # First get all user selections
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
    config["output_language"] = selections.get("output_language", "English")
    config["checkpoint_enabled"] = checkpoint
    if config.get("market_scope") == "india" and selections["asset_type"] == "stock":
        selections["ticker"] = validate_india_symbol_or_raise(selections["ticker"], config)

    # Create stats callback handler for tracking LLM/tool calls
    stats_handler = StatsCallbackHandler()

    # Normalize analyst selection to predefined order (selection is a 'set', order is fixed)
    selected_set = {analyst.value for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]
    analyst_execution_plan = build_analyst_execution_plan(
        selected_analyst_keys,
        concurrency_limit=config["analyst_concurrency_limit"],
    )
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
    safe_ticker = safe_india_ticker_component(selections["ticker"]) if config.get("market_scope") == "india" else selections["ticker"]
    results_dir = Path(config["results_dir"]) / safe_ticker / selections["analysis_date"]
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

    with Live(layout, refresh_per_second=4) as live:
        # Initial display
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

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

        # Streamed chunks are per-node deltas, not full state. Merge them
        # so every report field populated across the run is present.
        final_state = {}
        for chunk in trace:
            final_state.update(chunk)
        decision = graph.process_signal(final_state["final_trade_decision"])

        # Update all agent statuses to completed
        for agent in message_buffer.agent_status:
            message_buffer.update_agent_status(agent, "completed")

        message_buffer.add_message(
            "System", f"Completed analysis for {selections['analysis_date']}"
        )
        message_buffer.add_message("System", analyst_wall_time_tracker.format_summary())

        # Update final report sections
        for section in message_buffer.report_sections.keys():
            if section in final_state:
                message_buffer.update_report_section(section, final_state[section])

        update_display(layout, stats_handler=stats_handler, start_time=start_time)

    # Post-analysis prompts (outside Live context for clean interaction)
    console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")
    console.print(f"[dim]{analyst_wall_time_tracker.format_summary()}[/dim]")

    # Prompt to save report
    save_choice = typer.prompt("Save report?", default="Y").strip().upper()
    if save_choice in ("Y", "YES", ""):
        default_path = Path.cwd() / "reports" / safe_ticker / selections["analysis_date"]
        save_path_str = typer.prompt(
            "Save path (press Enter for default)",
            default=str(default_path)
        ).strip()
        save_path = Path(save_path_str)
        try:
            report_file = save_report_to_disk(final_state, selections["ticker"], save_path)
            console.print(f"\n[green]✓ Report saved to:[/green] {save_path.resolve()}")
            console.print(f"  [dim]Complete report:[/dim] {report_file.name}")
        except Exception as e:
            console.print(f"[red]Error saving report: {e}[/red]")

    # Prompt to display full report
    display_choice = typer.prompt("\nDisplay full report on screen?", default="Y").strip().upper()
    if display_choice in ("Y", "YES", ""):
        display_complete_report(final_state)


def _parse_analysts_option(analysts: Optional[str]) -> list[str]:
    if not analysts:
        return INDIA_DEFAULT_ANALYSTS if DEFAULT_CONFIG.get("market_scope") == "india" else ["market", "social", "news", "fundamentals"]
    selected = [item.strip() for item in analysts.split(",") if item.strip()]
    build_analyst_execution_plan(selected)
    return selected


def run_doctor_checks(ticker: str = "RELIANCE.NS") -> dict:
    checks = {}
    checks["python"] = True
    checks["package_import"] = True
    try:
        normalized = validate_india_symbol_or_raise(ticker, DEFAULT_CONFIG)
        checks["ticker_validation"] = normalized
    except IndiaSymbolError as exc:
        checks["ticker_validation"] = f"failed: {exc}"
    cache_dir = Path(DEFAULT_CONFIG["data_cache_dir"])
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        probe = cache_dir / ".doctor_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks["cache_dir_writable"] = str(cache_dir)
    except Exception as exc:  # noqa: BLE001 - health-check output should be readable.
        checks["cache_dir_writable"] = f"failed: {exc}"
    for provider, env_var in {
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "alpha_vantage": "ALPHA_VANTAGE_API_KEY",
    }.items():
        checks[f"{provider}_key_present"] = bool(os.environ.get(env_var))
    return checks


def run_first_run_checks(
    ticker: str = "RELIANCE.NS",
    analysis_date: str = "2026-06-05",
    analysts: Optional[str] = None,
    provider: Optional[str] = None,
) -> dict:
    """Return offline readiness checks for the recommended first research pack."""
    config = DEFAULT_CONFIG.copy()
    if provider:
        config["llm_provider"] = provider.lower()

    checks = []

    def add_check(name: str, status: str, detail: str, next_step: str = "") -> None:
        checks.append(
            {
                "name": name,
                "status": status,
                "detail": detail,
                "next_step": next_step,
            }
        )

    normalized_ticker = None
    try:
        normalized_ticker = validate_india_symbol_or_raise(ticker, config)
        add_check("Ticker", "pass", normalized_ticker)
    except IndiaSymbolError as exc:
        add_check(
            "Ticker",
            "fail",
            str(exc),
            "Use an India ticker such as RELIANCE.NS or RELIANCE.BO.",
        )

    resolved_date = None
    try:
        resolved_date, warnings = resolve_india_analysis_date(analysis_date)
        detail = resolved_date
        if warnings:
            detail = f"{resolved_date}; warnings: {'; '.join(warnings)}"
        add_check("Analysis date", "pass", detail)
    except IndiaCalendarError as exc:
        add_check(
            "Analysis date",
            "fail",
            str(exc),
            "Use a valid India market date on or before today.",
        )

    try:
        selected_analysts = _parse_analysts_option(analysts)
        add_check("Analyst selection", "pass", ", ".join(selected_analysts))
    except ValueError as exc:
        add_check(
            "Analyst selection",
            "fail",
            str(exc),
            "Use analyst keys such as india_market,india_fundamentals.",
        )

    provider_key = config["llm_provider"]
    key_env = get_api_key_env(provider_key)
    if key_env is None:
        if provider_key == "ollama":
            add_check("LLM credentials", "pass", "ollama does not require an API key")
        else:
            add_check(
                "LLM credentials",
                "fail",
                f"Unknown or unsupported provider '{provider_key}' for preflight.",
                "Use --provider openai, google, anthropic, or ollama.",
            )
    elif os.environ.get(key_env):
        add_check("LLM credentials", "pass", f"{key_env} is set")
    else:
        add_check(
            "LLM credentials",
            "fail",
            f"{key_env} is not set for provider '{provider_key}'.",
            "Add the key to .env or export it before running analyze.",
        )

    if normalized_ticker and resolved_date:
        report_path = (
            Path.cwd()
            / "reports"
            / safe_india_ticker_component(normalized_ticker)
            / resolved_date
        )
        add_check("Report path", "pass", str(report_path))

    return {
        "ready": all(check["status"] == "pass" for check in checks),
        "ticker": normalized_ticker,
        "analysis_date": resolved_date,
        "provider": provider_key,
        "checks": checks,
    }


def _sample_section(title: str, symbol: str) -> str:
    return (
        "SAMPLE ONLY - UNAVAILABLE: This section was generated by the offline "
        "`sample-report` workflow. It did not use live market data, official "
        "exchange filings, local filings, or an LLM.\n\n"
        f"Symbol: {symbol}\n\n"
        "Source: IndiaMarketAgents offline sample placeholder\n"
        "Data Quality: unavailable\n"
        "Confidence: unavailable\n"
        "Coverage: no factual market coverage\n"
        "Limitations: use this artifact only to verify report saving, dashboard "
        "review, and compliance/disclaimer workflow.\n\n"
        f"Reviewer note: replace this placeholder with a real {title} section "
        "only after running a credentialed analysis and verifying claims against "
        "official filings or user-supplied documents."
    )


def build_sample_report_state(ticker: str, analysis_date: str) -> dict:
    """Build an explicit no-data sample report state for workflow rehearsal."""
    return {
        "trade_date": analysis_date,
        "india_market_report": _sample_section("market technical", ticker),
        "india_fundamentals_report": _sample_section("fundamentals", ticker),
        "india_news_filings_report": _sample_section("news and filings", ticker),
        "india_macro_policy_report": _sample_section("macro and policy", ticker),
        "india_flows_report": _sample_section("flows and positioning", ticker),
        "india_compliance_report": _sample_section("compliance", ticker),
        "india_sentiment_report": _sample_section("sentiment", ticker),
        "trader_investment_plan": (
            "SAMPLE MODEL VIEW - UNAVAILABLE: No model or analyst output was "
            "used. This is not a trade instruction, recommendation, or "
            "investment advice.\n\n"
            "Source: IndiaMarketAgents offline sample placeholder\n"
            "Data Quality: unavailable\n"
            "Confidence: unavailable"
        ),
        "final_trade_decision": (
            "SAMPLE PORTFOLIO RESEARCH VIEW - UNAVAILABLE: No portfolio "
            "judgment was produced. Use this file only to verify saved-report "
            "review workflow.\n\n"
            "Source: IndiaMarketAgents offline sample placeholder\n"
            "Data Quality: unavailable\n"
            "Confidence: unavailable"
        ),
        "investment_debate_state": {
            "bull_history": _sample_section("bull case", ticker),
            "bear_history": _sample_section("bear case", ticker),
            "judge_decision": _sample_section("research manager view", ticker),
        },
        "risk_debate_state": {
            "aggressive_history": _sample_section("aggressive risk view", ticker),
            "conservative_history": _sample_section("conservative risk view", ticker),
            "neutral_history": _sample_section("neutral risk view", ticker),
        },
    }


def generate_sample_report(
    ticker: str = "RELIANCE.NS",
    analysis_date: str = "2026-06-05",
    save_path: Optional[Path] = None,
) -> Path:
    """Generate a sample saved-report bundle without LLM or market calls."""
    normalized_ticker = validate_india_symbol_or_raise(ticker, DEFAULT_CONFIG)
    resolved_date, warnings = resolve_india_analysis_date(analysis_date)
    for warning in warnings:
        console.print(f"[yellow]{warning}[/yellow]")
    final_state = build_sample_report_state(normalized_ticker, resolved_date)
    target_path = save_path or (
        Path.cwd()
        / "reports"
        / safe_india_ticker_component(normalized_ticker)
        / resolved_date
    )
    return save_report_to_disk(final_state, normalized_ticker, target_path)


def run_noninteractive_analysis(
    *,
    ticker: str,
    analysis_date: str,
    analysts: Optional[str],
    provider: Optional[str],
    quick_model: Optional[str],
    deep_model: Optional[str],
    research_depth: int,
    checkpoint: bool,
    save_path: Optional[Path],
    no_display: bool,
    no_save_prompt: bool,
):
    config = DEFAULT_CONFIG.copy()
    config["checkpoint_enabled"] = checkpoint
    config["max_debate_rounds"] = research_depth
    config["max_risk_discuss_rounds"] = research_depth
    if provider:
        config["llm_provider"] = provider.lower()
    if quick_model:
        config["quick_think_llm"] = quick_model
    if deep_model:
        config["deep_think_llm"] = deep_model

    normalized_ticker = validate_india_symbol_or_raise(ticker, config)
    resolved_date, warnings = resolve_india_analysis_date(analysis_date)
    for warning in warnings:
        console.print(f"[yellow]{warning}[/yellow]")

    selected_analysts = _parse_analysts_option(analysts)
    key_env = get_api_key_env(config["llm_provider"])
    if key_env and not os.environ.get(key_env):
        raise ValueError(
            f"{key_env} is not set for provider '{config['llm_provider']}'. "
            "Add it to .env or export it before running analysis."
        )
    graph = TradingAgentsGraph(selected_analysts, config=config, debug=False)
    final_state, decision = graph.propagate(normalized_ticker, resolved_date)
    final_state["trade_date"] = resolved_date

    target_path = save_path or (Path.cwd() / "reports" / safe_india_ticker_component(normalized_ticker) / resolved_date)
    report_file = save_report_to_disk(final_state, normalized_ticker, target_path)
    console.print(f"[green]Report saved:[/green] {report_file.resolve()}")
    if not no_display:
        display_complete_report(final_state)
    return decision


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context):
    """Launch interactive analysis when no subcommand is provided."""
    if ctx.invoked_subcommand is None:
        run_analysis()


@app.command()
def analyze(
    ticker: Optional[str] = typer.Option(
        None,
        "--ticker",
        help="NSE/BSE ticker such as RELIANCE.NS. When omitted, launches the interactive beginner flow.",
    ),
    analysis_date: Optional[str] = typer.Option(
        None,
        "--date",
        help="Analysis date in YYYY-MM-DD format. Future dates are rejected; India weekends roll back.",
    ),
    analysts: Optional[str] = typer.Option(
        None,
        "--analysts",
        help="Comma-separated analyst keys, e.g. india_market,india_fundamentals,india_news_filings.",
    ),
    provider: Optional[str] = typer.Option(None, "--provider", help="LLM provider key, e.g. openai."),
    quick_model: Optional[str] = typer.Option(None, "--quick-model", help="Quick-thinking model ID."),
    deep_model: Optional[str] = typer.Option(None, "--deep-model", help="Deep-thinking model ID."),
    research_depth: int = typer.Option(1, "--research-depth", help="Debate/risk rounds."),
    checkpoint: bool = typer.Option(
        False,
        "--checkpoint",
        help="Enable checkpoint/resume: save state after each node so a crashed run can resume.",
    ),
    save_path: Optional[Path] = typer.Option(None, "--save-path", help="Directory for saved report files."),
    no_display: bool = typer.Option(False, "--no-display", help="Do not print the final report."),
    no_save_prompt: bool = typer.Option(False, "--no-save-prompt", help="Skip save prompts; non-interactive runs still save by default."),
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
    if ticker:
        if not analysis_date:
            raise typer.BadParameter("--date is required when --ticker is provided")
        try:
            run_noninteractive_analysis(
                ticker=ticker,
                analysis_date=analysis_date,
                analysts=analysts,
                provider=provider,
                quick_model=quick_model,
                deep_model=deep_model,
                research_depth=research_depth,
                checkpoint=checkpoint,
                save_path=save_path,
                no_display=no_display,
                no_save_prompt=no_save_prompt,
            )
        except (IndiaSymbolError, IndiaCalendarError, ValueError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(1) from exc
        return
    run_analysis(checkpoint=checkpoint)


@app.command()
def doctor(
    ticker: str = typer.Option("RELIANCE.NS", "--ticker", help="Ticker to validate during health check."),
):
    """Run a local health check without live LLM calls."""
    checks = run_doctor_checks(ticker)
    table = Table(title="IndiaMarketAgents Doctor", box=box.SIMPLE_HEAD)
    table.add_column("Check", style="cyan")
    table.add_column("Result", style="green")
    for key, value in checks.items():
        table.add_row(key, str(value))
    console.print(table)


@app.command("first-run-check")
def first_run_check(
    ticker: str = typer.Option(
        "RELIANCE.NS",
        "--ticker",
        help="Ticker for the first research pack.",
    ),
    analysis_date: str = typer.Option(
        "2026-06-05",
        "--date",
        help="Analysis date in YYYY-MM-DD format.",
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="LLM provider key to validate, e.g. openai.",
    ),
    analysts: Optional[str] = typer.Option(
        None,
        "--analysts",
        help="Comma-separated analyst keys to preflight.",
    ),
):
    """Check first-run readiness without live market, broker, or LLM calls."""
    result = run_first_run_checks(
        ticker=ticker,
        analysis_date=analysis_date,
        analysts=analysts,
        provider=provider,
    )
    table = Table(title="IndiaMarketAgents First Run Check", box=box.SIMPLE_HEAD)
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Detail")
    table.add_column("Next step")
    for check in result["checks"]:
        status = (
            "[green]PASS[/green]"
            if check["status"] == "pass"
            else "[red]FAIL[/red]"
        )
        table.add_row(check["name"], status, check["detail"], check["next_step"])
    console.print(table)
    if result["ready"]:
        console.print("[green]Ready for the first IndiaMarketAgents research run.[/green]")
    else:
        console.print("[red]Not ready for the first research run. Fix failed checks first.[/red]")
        raise typer.Exit(1)


@app.command("sample-report")
def sample_report(
    ticker: str = typer.Option(
        "RELIANCE.NS",
        "--ticker",
        help="Ticker for the sample saved-report bundle.",
    ),
    analysis_date: str = typer.Option(
        "2026-06-05",
        "--date",
        help="Analysis date in YYYY-MM-DD format.",
    ),
    save_path: Optional[Path] = typer.Option(
        None,
        "--save-path",
        help="Directory for the generated sample report bundle.",
    ),
):
    """Generate a no-data sample report bundle for dashboard/workflow review."""
    try:
        report_file = generate_sample_report(
            ticker=ticker,
            analysis_date=analysis_date,
            save_path=save_path,
        )
    except (IndiaSymbolError, IndiaCalendarError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]Sample report saved:[/green] {report_file.resolve()}")
    console.print(
        "[yellow]Sample only: no live market data, filings, broker access, or "
        "LLM analysis was used.[/yellow]"
    )


if __name__ == "__main__":
    app()
