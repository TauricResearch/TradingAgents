from typing import Optional
import datetime
import re
import typer
from pathlib import Path
from functools import wraps
from rich.console import Console
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
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
from tradingagents.default_config import DEFAULT_CONFIG
from cli.models import AnalystType
from cli.utils import *
from cli.announcements import fetch_announcements, display_announcements
from cli.stats_handler import StatsCallbackHandler

console = Console()

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents CLI: Swing Trading with Multi-Agent LLM Framework",
    add_completion=True,
)


class MessageBuffer:
    """Tracks agent status and reports during swing trading analysis."""

    # Fixed agents (always run after analysts)
    FIXED_AGENTS = {
        "Trading Team": ["Trader"],
    }

    # Analyst name mapping
    ANALYST_MAPPING = {
        "market": "Market Analyst",
        "news": "News Analyst",
        "fundamentals": "Fundamentals Analyst",
    }

    # Report sections: section -> (analyst_key for filtering, finalizing_agent)
    REPORT_SECTIONS = {
        "market_report": ("market", "Market Analyst"),
        "news_report": ("news", "News Analyst"),
        "fundamentals_report": ("fundamentals", "Fundamentals Analyst"),
        "trader_decision": (None, "Trader"),
    }

    def __init__(self, max_length=100):
        self.messages = deque(maxlen=max_length)
        self.tool_calls = deque(maxlen=max_length)
        self.current_report = None
        self.final_report = None
        self.agent_status = {}
        self.current_agent = None
        self.report_sections = {}
        self.selected_analysts = []
        self._last_message_id = None

    def init_for_analysis(self, selected_analysts):
        """Initialize agent status and report sections."""
        self.selected_analysts = [a.lower() for a in selected_analysts]

        self.agent_status = {}

        # Add selected analysts
        for analyst_key in self.selected_analysts:
            if analyst_key in self.ANALYST_MAPPING:
                self.agent_status[self.ANALYST_MAPPING[analyst_key]] = "pending"

        # Add fixed agents
        for team_agents in self.FIXED_AGENTS.values():
            for agent in team_agents:
                self.agent_status[agent] = "pending"

        # Build report_sections
        self.report_sections = {}
        for section, (analyst_key, _) in self.REPORT_SECTIONS.items():
            if analyst_key is None or analyst_key in self.selected_analysts:
                self.report_sections[section] = None

        # Reset
        self.current_report = None
        self.final_report = None
        self.current_agent = None
        self.messages.clear()
        self.tool_calls.clear()
        self._last_message_id = None

    def get_completed_reports_count(self):
        count = 0
        for section in self.report_sections:
            if section not in self.REPORT_SECTIONS:
                continue
            _, finalizing_agent = self.REPORT_SECTIONS[section]
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
        latest_section = None
        latest_content = None

        for section, content in self.report_sections.items():
            if content is not None:
                latest_section = section
                latest_content = content

        if latest_section and latest_content:
            section_titles = {
                "market_report": "Market Analysis (기술적 분석)",
                "news_report": "News Analysis (뉴스 분석)",
                "fundamentals_report": "Fundamentals Analysis (기본적 분석)",
                "trader_decision": "Swing Trading Decision (매매 결정)",
            }
            title = section_titles.get(latest_section, latest_section)
            self.current_report = f"### {title}\n{latest_content}"

        self._update_final_report()

    def _update_final_report(self):
        report_parts = []

        analyst_sections = ["market_report", "news_report", "fundamentals_report"]
        if any(self.report_sections.get(section) for section in analyst_sections):
            report_parts.append("## Analyst Reports")
            if self.report_sections.get("market_report"):
                report_parts.append(
                    f"### Market Analysis\n{self.report_sections['market_report']}"
                )
            if self.report_sections.get("news_report"):
                report_parts.append(
                    f"### News Analysis\n{self.report_sections['news_report']}"
                )
            if self.report_sections.get("fundamentals_report"):
                report_parts.append(
                    f"### Fundamentals Analysis\n{self.report_sections['fundamentals_report']}"
                )

        if self.report_sections.get("trader_decision"):
            report_parts.append("## Swing Trading Decision")
            report_parts.append(f"{self.report_sections['trader_decision']}")

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
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def update_display(layout, spinner_text=None, stats_handler=None, start_time=None):
    # Header
    layout["header"].update(
        Panel(
            "[bold green]TradingAgents - Swing Trading[/bold green]\n"
            "[dim]Analysts \u2192 Trader \u2192 Decision[/dim]",
            title="Swing Trading Pipeline",
            border_style="green",
            padding=(1, 2),
            expand=True,
        )
    )

    # Progress panel
    progress_table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        box=box.SIMPLE_HEAD,
        padding=(0, 2),
        expand=True,
    )
    progress_table.add_column("Team", style="cyan", justify="center", width=20)
    progress_table.add_column("Agent", style="green", justify="center", width=20)
    progress_table.add_column("Status", style="yellow", justify="center", width=20)

    all_teams = {
        "Analyst Team": ["Market Analyst", "News Analyst", "Fundamentals Analyst"],
        "Trading Team": ["Trader"],
    }

    teams = {}
    for team, agents in all_teams.items():
        active_agents = [a for a in agents if a in message_buffer.agent_status]
        if active_agents:
            teams[team] = active_agents

    for team, agents in teams.items():
        first_agent = agents[0]
        status = message_buffer.agent_status.get(first_agent, "pending")
        if status == "in_progress":
            status_cell = Spinner("dots", text="[blue]in_progress[/blue]", style="bold cyan")
        else:
            status_color = {"pending": "yellow", "completed": "green", "error": "red"}.get(status, "white")
            status_cell = f"[{status_color}]{status}[/{status_color}]"
        progress_table.add_row(team, first_agent, status_cell)

        for agent in agents[1:]:
            status = message_buffer.agent_status.get(agent, "pending")
            if status == "in_progress":
                status_cell = Spinner("dots", text="[blue]in_progress[/blue]", style="bold cyan")
            else:
                status_color = {"pending": "yellow", "completed": "green", "error": "red"}.get(status, "white")
                status_cell = f"[{status_color}]{status}[/{status_color}]"
            progress_table.add_row("", agent, status_cell)

        progress_table.add_row("\u2500" * 20, "\u2500" * 20, "\u2500" * 20, style="dim")

    layout["progress"].update(
        Panel(progress_table, title="Progress", border_style="cyan", padding=(1, 2))
    )

    # Messages panel
    messages_table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        expand=True,
        box=box.MINIMAL,
        show_lines=True,
        padding=(0, 1),
    )
    messages_table.add_column("Time", style="cyan", width=8, justify="center")
    messages_table.add_column("Type", style="green", width=10, justify="center")
    messages_table.add_column("Content", style="white", no_wrap=False, ratio=1)

    all_messages = []
    for timestamp, tool_name, args in message_buffer.tool_calls:
        formatted_args = format_tool_args(args)
        all_messages.append((timestamp, "Tool", f"{tool_name}: {formatted_args}"))
    for timestamp, msg_type, content in message_buffer.messages:
        content_str = str(content) if content else ""
        if len(content_str) > 200:
            content_str = content_str[:197] + "..."
        all_messages.append((timestamp, msg_type, content_str))

    all_messages.sort(key=lambda x: x[0], reverse=True)
    for timestamp, msg_type, content in all_messages[:12]:
        wrapped_content = Text(content, overflow="fold")
        messages_table.add_row(timestamp, msg_type, wrapped_content)

    layout["messages"].update(
        Panel(messages_table, title="Messages & Tools", border_style="blue", padding=(1, 2))
    )

    # Analysis panel
    if message_buffer.current_report:
        layout["analysis"].update(
            Panel(Markdown(message_buffer.current_report), title="Current Report", border_style="green", padding=(1, 2))
        )
    else:
        layout["analysis"].update(
            Panel("[italic]Waiting for analysis...[/italic]", title="Current Report", border_style="green", padding=(1, 2))
        )

    # Footer
    agents_completed = sum(1 for s in message_buffer.agent_status.values() if s == "completed")
    agents_total = len(message_buffer.agent_status)
    reports_completed = message_buffer.get_completed_reports_count()
    reports_total = len(message_buffer.report_sections)

    stats_parts = [f"Agents: {agents_completed}/{agents_total}"]
    if stats_handler:
        stats = stats_handler.get_stats()
        stats_parts.append(f"LLM: {stats['llm_calls']}")
        stats_parts.append(f"Tools: {stats['tool_calls']}")
        if stats["tokens_in"] > 0 or stats["tokens_out"] > 0:
            stats_parts.append(f"Tokens: {format_tokens(stats['tokens_in'])}\u2191 {format_tokens(stats['tokens_out'])}\u2193")
        else:
            stats_parts.append("Tokens: --")
    stats_parts.append(f"Reports: {reports_completed}/{reports_total}")
    if start_time:
        elapsed = time.time() - start_time
        stats_parts.append(f"\u23f1 {int(elapsed // 60):02d}:{int(elapsed % 60):02d}")

    stats_table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
    stats_table.add_column("Stats", justify="center")
    stats_table.add_row(" | ".join(stats_parts))
    layout["footer"].update(Panel(stats_table, border_style="grey50"))


def get_user_selections():
    """Get all user selections before starting analysis."""
    # Display welcome
    try:
        with open("./cli/static/welcome.txt", "r") as f:
            welcome_ascii = f.read()
    except FileNotFoundError:
        welcome_ascii = ""

    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgents: Swing Trading Framework[/bold green]\n\n"
    welcome_content += "[bold]Pipeline:[/bold] Analysts \u2192 Trader \u2192 Swing Decision\n\n"
    welcome_content += "[dim]Built by [Tauric Research](https://github.com/TauricResearch)[/dim]"

    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="Swing Trading Pipeline",
    )
    console.print(Align.center(welcome_box))
    console.print()

    announcements = fetch_announcements()
    display_announcements(console, announcements)

    def create_question_box(title, prompt, default=None):
        box_content = f"[bold]{title}[/bold]\n[dim]{prompt}[/dim]"
        if default:
            box_content += f"\n[dim]Default: {default}[/dim]"
        return Panel(box_content, border_style="blue", padding=(1, 2))

    # Step 1: Ticker
    console.print(create_question_box("Step 1: Ticker Symbol", "Enter the ticker symbol to analyze", "SPY"))
    selected_ticker = get_ticker()

    # Step 2: Date
    default_date = datetime.datetime.now().strftime("%Y-%m-%d")
    console.print(create_question_box("Step 2: Analysis Date", "Enter the analysis date (YYYY-MM-DD)", default_date))
    analysis_date = get_analysis_date()

    # Step 3: Analysts
    console.print(create_question_box("Step 3: Analysts", "Select analysts for the analysis"))
    selected_analysts = select_analysts()
    console.print(f"[green]Selected:[/green] {', '.join(a.value for a in selected_analysts)}")

    # Step 4: LLM provider
    console.print(create_question_box("Step 4: LLM Provider", "Select which LLM service to use"))
    selected_llm_provider, backend_url = select_llm_provider()

    # Step 5: LLM models
    console.print(create_question_box("Step 5: LLM Models", "Select your thinking agents"))
    selected_shallow_thinker = select_shallow_thinking_agent(selected_llm_provider)
    selected_deep_thinker = select_deep_thinking_agent(selected_llm_provider)

    # Step 6: Provider-specific config
    thinking_level = None
    reasoning_effort = None
    provider_lower = selected_llm_provider.lower()
    if provider_lower == "google":
        console.print(create_question_box("Step 6: Thinking Mode", "Configure Gemini thinking mode"))
        thinking_level = ask_gemini_thinking_config()
    elif provider_lower == "openai":
        console.print(create_question_box("Step 6: Reasoning Effort", "Configure OpenAI reasoning effort"))
        reasoning_effort = ask_openai_reasoning_effort()

    return {
        "ticker": selected_ticker,
        "analysis_date": analysis_date,
        "analysts": selected_analysts,
        "llm_provider": selected_llm_provider.lower(),
        "backend_url": backend_url,
        "shallow_thinker": selected_shallow_thinker,
        "deep_thinker": selected_deep_thinker,
        "google_thinking_level": thinking_level,
        "openai_reasoning_effort": reasoning_effort,
    }


def save_report_to_disk(final_state, ticker: str, save_path: Path):
    """Save swing trading report to disk."""
    save_path.mkdir(parents=True, exist_ok=True)
    sections = []

    # 1. Analyst reports
    analysts_dir = save_path / "1_analysts"
    analyst_parts = []
    if final_state.get("market_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "market.md").write_text(final_state["market_report"])
        analyst_parts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("news_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "news.md").write_text(final_state["news_report"])
        analyst_parts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "fundamentals.md").write_text(final_state["fundamentals_report"])
        analyst_parts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Reports\n\n{content}")

    # 2. Trader decision
    if final_state.get("trader_decision"):
        trading_dir = save_path / "2_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(final_state["trader_decision"])
        sections.append(f"## II. Swing Trading Decision\n\n### Trader\n{final_state['trader_decision']}")

    # Write consolidated report
    header = f"# Swing Trading Report: {ticker}\n\nGenerated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    (save_path / "complete_report.md").write_text(header + "\n\n".join(sections))
    return save_path / "complete_report.md"


def translate_report_to_korean(report_content: str, llm) -> str:
    """영문 트레이딩 분석 리포트를 한국어로 번역."""
    from langchain_core.messages import HumanMessage, SystemMessage

    system_prompt = (
        "당신은 금융 전문가이자 비전공자 교육 전문가입니다.\n"
        "영어 주식 트레이딩 분석 리포트를 한국어로 번역하고, "
        "금융·기술 전문 용어를 비전공자도 쉽게 이해할 수 있도록 설명을 추가해주세요.\n\n"
        "번역 지침:\n"
        "1. 자연스러운 한국어로 번역하세요.\n"
        "2. 처음 등장하는 전문 용어 뒤에 괄호로 쉬운 설명을 추가하세요.\n"
        "3. 복잡한 분석 개념은 일상적인 비유를 사용해 쉽게 설명하세요.\n"
        "4. 가격, 퍼센트 등 수치와 종목 코드는 그대로 유지하세요.\n"
        "5. 마크다운 형식을 그대로 유지하세요.\n"
        "6. 섹션 제목은 한국어로 번역하세요.\n"
        "7. 최종 투자 의견과 권고 사항을 명확히 전달하세요."
    )

    parts = re.split(r"(?=^## )", report_content, flags=re.MULTILINE)

    translated_parts = []
    for part in parts:
        if not part.strip():
            continue
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"아래 내용을 한국어로 번역하고 전문 용어를 쉽게 설명해주세요:\n\n{part}"),
        ])
        translated_parts.append(response.content)

    return "\n\n".join(translated_parts)


def display_complete_report(final_state):
    """Display the complete analysis report."""
    console.print()
    console.print(Rule("Swing Trading Report", style="bold green"))

    # Analyst Reports
    analysts = []
    if final_state.get("market_report"):
        analysts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("news_report"):
        analysts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analysts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
    if analysts:
        console.print(Panel("[bold]I. Analyst Reports[/bold]", border_style="cyan"))
        for title, content in analysts:
            console.print(Panel(Markdown(content), title=title, border_style="blue", padding=(1, 2)))

    # Trader Decision
    if final_state.get("trader_decision"):
        console.print(Panel("[bold]II. Swing Trading Decision[/bold]", border_style="yellow"))
        console.print(Panel(Markdown(final_state["trader_decision"]), title="Trader", border_style="blue", padding=(1, 2)))


# Ordered list of analysts for status transitions
ANALYST_ORDER = ["market", "news", "fundamentals"]
ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
ANALYST_REPORT_MAP = {
    "market": "market_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}


def update_analyst_statuses(message_buffer, chunk):
    """Update analyst statuses based on current report state."""
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

    # When all analysts done, set Trader to in_progress
    if not found_active and selected:
        if message_buffer.agent_status.get("Trader") == "pending":
            message_buffer.update_agent_status("Trader", "in_progress")


def extract_content_string(content):
    """Extract string content from various message formats."""
    import ast

    def is_empty(val):
        if val is None or val == '':
            return True
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return True
            try:
                return not bool(ast.literal_eval(s))
            except (ValueError, SyntaxError):
                return False
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
    """Classify LangChain message into display type and extract content."""
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
    return ("System", content)


def format_tool_args(args, max_length=80) -> str:
    result = str(args)
    if len(result) > max_length:
        return result[:max_length - 3] + "..."
    return result


def run_analysis():
    selections = get_user_selections()

    config = DEFAULT_CONFIG.copy()
    config["quick_think_llm"] = selections["shallow_thinker"]
    config["deep_think_llm"] = selections["deep_thinker"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()
    config["google_thinking_level"] = selections.get("google_thinking_level")
    config["openai_reasoning_effort"] = selections.get("openai_reasoning_effort")

    stats_handler = StatsCallbackHandler()

    # Normalize analyst selection to predefined order
    selected_set = {analyst.value for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]

    graph = TradingAgentsGraph(
        selected_analyst_keys,
        config=config,
        debug=True,
        callbacks=[stats_handler],
    )

    message_buffer.init_for_analysis(selected_analyst_keys)
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
            content = content.replace("\n", " ")
            with open(log_file, "a") as f:
                f.write(f"{timestamp} [{message_type}] {content}\n")
        return wrapper

    def save_tool_call_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, tool_name, args = obj.tool_calls[-1]
            args_str = ", ".join(f"{k}={v}" for k, v in args.items())
            with open(log_file, "a") as f:
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
                    with open(report_dir / f"{section_name}.md", "w") as f:
                        f.write(content)
        return wrapper

    message_buffer.add_message = save_message_decorator(message_buffer, "add_message")
    message_buffer.add_tool_call = save_tool_call_decorator(message_buffer, "add_tool_call")
    message_buffer.update_report_section = save_report_section_decorator(message_buffer, "update_report_section")

    layout = create_layout()

    with Live(layout, refresh_per_second=4) as live:
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        message_buffer.add_message("System", f"Ticker: {selections['ticker']}")
        message_buffer.add_message("System", f"Date: {selections['analysis_date']}")
        message_buffer.add_message("System", f"Analysts: {', '.join(a.value for a in selections['analysts'])}")
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # Set first analyst to in_progress
        first_analyst_key = selected_analyst_keys[0]
        first_analyst_name = ANALYST_AGENT_NAMES[first_analyst_key]
        message_buffer.update_agent_status(first_analyst_name, "in_progress")
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # Initialize state and stream
        init_state = graph.propagator.create_initial_state(
            selections["ticker"], selections["analysis_date"]
        )
        args = graph.propagator.get_graph_args(callbacks=[stats_handler])

        trace = []
        for chunk in graph.graph.stream(init_state, **args):
            # Process messages
            if len(chunk["messages"]) > 0:
                last_message = chunk["messages"][-1]
                msg_id = getattr(last_message, "id", None)

                if msg_id != message_buffer._last_message_id:
                    message_buffer._last_message_id = msg_id

                    msg_type, content = classify_message_type(last_message)
                    if content and content.strip():
                        message_buffer.add_message(msg_type, content)

                    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                        for tool_call in last_message.tool_calls:
                            if isinstance(tool_call, dict):
                                message_buffer.add_tool_call(tool_call["name"], tool_call["args"])
                            else:
                                message_buffer.add_tool_call(tool_call.name, tool_call.args)

            # Update analyst statuses
            update_analyst_statuses(message_buffer, chunk)

            # Trader decision
            if chunk.get("trader_decision"):
                message_buffer.update_report_section("trader_decision", chunk["trader_decision"])
                if message_buffer.agent_status.get("Trader") != "completed":
                    message_buffer.update_agent_status("Trader", "completed")

            update_display(layout, stats_handler=stats_handler, start_time=start_time)
            trace.append(chunk)

        # Get final state
        final_state = trace[-1]

        # Update all agents to completed
        for agent in message_buffer.agent_status:
            message_buffer.update_agent_status(agent, "completed")

        message_buffer.add_message("System", f"Analysis complete for {selections['ticker']}")

        for section in message_buffer.report_sections.keys():
            if section in final_state:
                message_buffer.update_report_section(section, final_state[section])

        update_display(layout, stats_handler=stats_handler, start_time=start_time)

    # Post-analysis
    console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")

    # Process swing signal
    swing_signal = graph.process_signal(final_state.get("trader_decision", ""))
    action = swing_signal.get("action", "PASS")
    console.print(f"[bold]Swing Decision:[/bold] [{'green' if action == 'BUY' else 'yellow' if action == 'SELL' else 'dim'}]{action}[/]")
    if action != "PASS":
        if swing_signal.get("entry_price"):
            console.print(f"  Entry: {swing_signal['entry_price']}")
        if swing_signal.get("stop_loss"):
            console.print(f"  Stop Loss: {swing_signal['stop_loss']}")
        if swing_signal.get("take_profit"):
            console.print(f"  Take Profit: {swing_signal['take_profit']}")
        if swing_signal.get("position_size_pct"):
            console.print(f"  Position Size: {swing_signal['position_size_pct']*100:.0f}%")
        if swing_signal.get("max_hold_days"):
            console.print(f"  Max Hold: {swing_signal['max_hold_days']} days")

    # Save report
    save_choice = typer.prompt("\nSave report?", default="Y").strip().upper()
    if save_choice in ("Y", "YES", ""):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = Path.cwd() / "reports" / f"{selections['ticker']}_{timestamp}"
        save_path_str = typer.prompt("Save path (Enter for default)", default=str(default_path)).strip()
        save_path = Path(save_path_str)
        report_file = None
        try:
            report_file = save_report_to_disk(final_state, selections["ticker"], save_path)
            console.print(f"\n[green]\u2713 Report saved:[/green] {save_path.resolve()}")
        except Exception as e:
            console.print(f"[red]Error saving report: {e}[/red]")

        # Korean translation
        if report_file and report_file.exists():
            ko_choice = typer.prompt("\n한국어 번역 리포트 생성?", default="Y").strip().upper()
            if ko_choice in ("Y", "YES", ""):
                console.print("\n[bold cyan]한국어로 번역 중...[/bold cyan]")
                try:
                    korean_content = translate_report_to_korean(
                        report_file.read_text(), graph.deep_thinking_llm
                    )
                    ko_header = (
                        f"# 스윙 트레이딩 리포트: {selections['ticker']} (한국어)\n\n"
                        f"생성: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n"
                    )
                    ko_file = save_path / "complete_report_ko.md"
                    ko_file.write_text(ko_header + korean_content)
                    console.print(f"[green]\u2713 한국어 번역 완료:[/green] {ko_file.name}")
                except Exception as e:
                    console.print(f"[red]번역 오류: {e}[/red]")

    # Display full report
    display_choice = typer.prompt("\nDisplay full report?", default="Y").strip().upper()
    if display_choice in ("Y", "YES", ""):
        display_complete_report(final_state)


@app.command()
def analyze():
    """Analyze a single ticker (manual input)."""
    run_analysis()


@app.command()
def swing():
    """Full swing trading pipeline: Screen stocks → Analyze candidates → Trading decisions."""
    run_swing_pipeline()


def _get_swing_config():
    """Get config selections for swing pipeline (no ticker needed)."""
    try:
        with open("./cli/static/welcome.txt", "r") as f:
            welcome_ascii = f.read()
    except FileNotFoundError:
        welcome_ascii = ""

    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgents: Swing Trading Pipeline[/bold green]\n\n"
    welcome_content += "[bold]Pipeline:[/bold] Screening → Analysts → Trader → Swing Decision\n\n"
    welcome_content += "[dim]Built by [Tauric Research](https://github.com/TauricResearch)[/dim]"

    console.print(Align.center(Panel(
        welcome_content, border_style="green", padding=(1, 2), title="Swing Trading Pipeline",
    )))
    console.print()

    announcements = fetch_announcements()
    display_announcements(console, announcements)

    def create_question_box(title, prompt, default=None):
        box_content = f"[bold]{title}[/bold]\n[dim]{prompt}[/dim]"
        if default:
            box_content += f"\n[dim]Default: {default}[/dim]"
        return Panel(box_content, border_style="blue", padding=(1, 2))

    # Step 1: Date
    default_date = datetime.datetime.now().strftime("%Y-%m-%d")
    console.print(create_question_box("Step 1: Trading Date", "Enter the trading date", default_date))
    analysis_date = get_analysis_date()

    # Step 2: Market
    import questionary
    console.print(create_question_box("Step 2: Market", "Select target market"))
    market_choice = questionary.select(
        "Select Market:",
        choices=["KRX (한국)", "US (미국)"],
        style=questionary.Style([("selected", "fg:green noinherit"), ("highlighted", "fg:green noinherit")]),
    ).ask()
    market = "KRX" if "KRX" in (market_choice or "KRX") else "US"

    # Step 3: Analysts
    console.print(create_question_box("Step 3: Analysts", "Select analysts for candidate analysis"))
    selected_analysts = select_analysts()

    # Step 4: LLM
    console.print(create_question_box("Step 4: LLM Provider", "Select LLM service"))
    selected_llm_provider, backend_url = select_llm_provider()

    # Step 5: Models
    console.print(create_question_box("Step 5: LLM Models", "Select thinking agents"))
    selected_shallow_thinker = select_shallow_thinking_agent(selected_llm_provider)
    selected_deep_thinker = select_deep_thinking_agent(selected_llm_provider)

    # Step 6: Provider config
    thinking_level = None
    reasoning_effort = None
    provider_lower = selected_llm_provider.lower()
    if provider_lower == "google":
        console.print(create_question_box("Step 6: Thinking Mode", "Configure Gemini"))
        thinking_level = ask_gemini_thinking_config()
    elif provider_lower == "openai":
        console.print(create_question_box("Step 6: Reasoning Effort", "Configure OpenAI"))
        reasoning_effort = ask_openai_reasoning_effort()

    return {
        "analysis_date": analysis_date,
        "market": market,
        "analysts": selected_analysts,
        "llm_provider": selected_llm_provider.lower(),
        "backend_url": backend_url,
        "shallow_thinker": selected_shallow_thinker,
        "deep_thinker": selected_deep_thinker,
        "google_thinking_level": thinking_level,
        "openai_reasoning_effort": reasoning_effort,
    }


def _display_swing_signal(ticker: str, name: str, swing_signal: dict):
    """Display a single swing signal result."""
    action = swing_signal.get("action", "PASS")
    color = {"BUY": "green", "SELL": "yellow", "HOLD": "cyan"}.get(action, "dim")

    parts = [f"[bold][{color}]{action}[/{color}][/bold] {name} ({ticker})"]
    if action != "PASS":
        details = []
        if swing_signal.get("entry_price"):
            details.append(f"진입가: {swing_signal['entry_price']}")
        if swing_signal.get("stop_loss"):
            details.append(f"손절: {swing_signal['stop_loss']}")
        if swing_signal.get("take_profit"):
            details.append(f"익절: {swing_signal['take_profit']}")
        if swing_signal.get("position_size_pct"):
            details.append(f"비중: {swing_signal['position_size_pct']*100:.0f}%")
        if swing_signal.get("max_hold_days"):
            details.append(f"보유: {swing_signal['max_hold_days']}일")
        if details:
            parts.append("  " + " | ".join(details))
        if swing_signal.get("rationale"):
            parts.append(f"  사유: {swing_signal['rationale']}")

    for part in parts:
        console.print(part)


def run_swing_pipeline():
    """Run full swing pipeline: screen → analyze → decide."""
    selections = _get_swing_config()

    config = DEFAULT_CONFIG.copy()
    config["market"] = selections["market"]
    config["quick_think_llm"] = selections["shallow_thinker"]
    config["deep_think_llm"] = selections["deep_thinker"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"]
    config["google_thinking_level"] = selections.get("google_thinking_level")
    config["openai_reasoning_effort"] = selections.get("openai_reasoning_effort")

    selected_set = {a.value for a in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]

    stats_handler = StatsCallbackHandler()
    graph = TradingAgentsGraph(
        selected_analyst_keys,
        config=config,
        debug=False,
        callbacks=[stats_handler],
    )

    trade_date = selections["analysis_date"]

    # ─── Phase 1: Screening ───
    console.print()
    console.print(Rule("Phase 1: Stock Screening (종목 발굴)", style="bold cyan"))
    console.print(f"[dim]Market: {selections['market']} / Date: {trade_date}[/dim]\n")

    with console.status("[bold cyan]Scanning market universe...[/bold cyan]"):
        screening_result = graph.screen(trade_date=trade_date)

    # Display screening report
    console.print(Panel(
        screening_result.get("report", "No report"),
        title="Screening Report",
        border_style="cyan",
        padding=(1, 2),
    ))

    candidates = screening_result.get("candidates", [])
    stats = screening_result.get("stats", {})
    console.print(
        f"\n[bold]Results:[/bold] {stats.get('universe_size', 0)} universe → "
        f"{stats.get('technical_passed', 0)} technical → "
        f"{stats.get('fundamental_passed', 0)} fundamental → "
        f"[bold green]{stats.get('final_selected', 0)} final candidates[/bold green]"
    )

    if not candidates:
        console.print("\n[yellow]No candidates found. Try adjusting screening criteria.[/yellow]")
        return

    # Ask to proceed
    proceed = typer.prompt(
        f"\n{len(candidates)}개 후보 종목을 분석하시겠습니까?", default="Y"
    ).strip().upper()
    if proceed not in ("Y", "YES", ""):
        return

    # ─── Phase 2: Analyze each candidate ───
    console.print()
    console.print(Rule("Phase 2: Candidate Analysis (후보 분석)", style="bold yellow"))

    all_results = []

    for i, candidate in enumerate(candidates, 1):
        ticker = candidate["ticker"]
        name = candidate.get("name", ticker)
        signals = ", ".join(candidate.get("signals", []))
        screening_context = (
            f"종목: {name} ({ticker})\n"
            f"기술적 신호: {signals}\n"
            f"펀더멘탈: {candidate.get('fundamental_check', 'N/A')}"
        )

        console.print(f"\n[bold]({i}/{len(candidates)}) {name} ({ticker})[/bold]")
        console.print(f"  [dim]{signals}[/dim]")

        try:
            with console.status(f"[bold cyan]Analyzing {ticker}...[/bold cyan]"):
                final_state, swing_signal = graph.propagate(
                    company_name=ticker,
                    trade_date=trade_date,
                    screening_context=screening_context,
                )

            _display_swing_signal(ticker, name, swing_signal)

            all_results.append({
                "ticker": ticker,
                "name": name,
                "swing_signal": swing_signal,
                "final_state": final_state,
                "screening_context": screening_context,
            })

        except Exception as e:
            console.print(f"  [red]Analysis failed: {e}[/red]")

    # ─── Phase 3: Summary ───
    console.print()
    console.print(Rule("Summary (종합 결과)", style="bold green"))

    buy_signals = [r for r in all_results if r["swing_signal"].get("action") == "BUY"]
    sell_signals = [r for r in all_results if r["swing_signal"].get("action") == "SELL"]
    pass_signals = [r for r in all_results if r["swing_signal"].get("action") in ("PASS", "HOLD")]

    # Summary table
    summary_table = Table(
        title="Swing Trading Signals",
        show_header=True,
        header_style="bold",
        box=box.ROUNDED,
        padding=(0, 1),
    )
    summary_table.add_column("Action", justify="center", width=8)
    summary_table.add_column("Ticker", justify="center", width=10)
    summary_table.add_column("Name", width=20)
    summary_table.add_column("Entry", justify="right", width=12)
    summary_table.add_column("Stop Loss", justify="right", width=12)
    summary_table.add_column("Take Profit", justify="right", width=12)
    summary_table.add_column("Size", justify="center", width=8)
    summary_table.add_column("Hold", justify="center", width=8)

    for r in all_results:
        sig = r["swing_signal"]
        action = sig.get("action", "PASS")
        color = {"BUY": "green", "SELL": "yellow"}.get(action, "dim")

        entry = str(sig.get("entry_price", "-"))
        sl = str(sig.get("stop_loss", "-"))
        tp = str(sig.get("take_profit", "-"))
        size = f"{sig['position_size_pct']*100:.0f}%" if sig.get("position_size_pct") else "-"
        hold = f"{sig['max_hold_days']}d" if sig.get("max_hold_days") else "-"

        summary_table.add_row(
            f"[{color}]{action}[/{color}]",
            r["ticker"], r["name"],
            entry, sl, tp, size, hold,
        )

    console.print(summary_table)
    console.print(f"\n[bold green]BUY: {len(buy_signals)}[/bold green] / "
                  f"[bold yellow]SELL: {len(sell_signals)}[/bold yellow] / "
                  f"[dim]PASS: {len(pass_signals)}[/dim]")

    # Save reports
    if all_results:
        save_choice = typer.prompt("\nSave reports?", default="Y").strip().upper()
        if save_choice in ("Y", "YES", ""):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base_path = Path.cwd() / "reports" / f"swing_{selections['market']}_{timestamp}"
            base_path.mkdir(parents=True, exist_ok=True)

            for r in all_results:
                try:
                    ticker_dir = base_path / r["ticker"]
                    save_report_to_disk(r["final_state"], r["ticker"], ticker_dir)
                except Exception as e:
                    console.print(f"[red]Error saving {r['ticker']}: {e}[/red]")

            # Save summary
            summary_lines = [
                f"# Swing Trading Summary: {selections['market']}",
                f"Date: {trade_date}",
                f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
            ]
            for r in all_results:
                sig = r["swing_signal"]
                summary_lines.append(f"## {r['name']} ({r['ticker']}) - {sig.get('action', 'PASS')}")
                if sig.get("rationale"):
                    summary_lines.append(f"사유: {sig['rationale']}")
                summary_lines.append("")

            (base_path / "summary.md").write_text("\n".join(summary_lines))
            console.print(f"\n[green]\u2713 Reports saved:[/green] {base_path.resolve()}")


if __name__ == "__main__":
    app()
