import ast
import datetime
import os
import time
from functools import wraps
from pathlib import Path

import typer
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule

from cli.announcements import display_announcements, fetch_announcements
from cli.live import (
    AgentStatusTracker,
    DisplayManager,
    MessageStore,
    ReportBuilder,
)
from cli.stats_handler import StatsCallbackHandler
from cli.utils import (
    ask_anthropic_effort,
    ask_gemini_thinking_config,
    ask_glm_region,
    ask_minimax_region,
    ask_openai_reasoning_effort,
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
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import (
    AnalystWallTimeTracker,
    build_analyst_execution_plan,
    get_initial_analyst_node,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree

console = Console()

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents CLI: Multi-Agents LLM Financial Trading Framework",
    add_completion=True,
)


# ---------------------------------------------------------------------------
# Helpers for message classification (used in the streaming loop)
# ---------------------------------------------------------------------------

def extract_content_string(content):
    """Extract string content from various message formats.
    Returns None if no meaningful text content is found.
    """
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


# ---------------------------------------------------------------------------
# User interaction
# ---------------------------------------------------------------------------

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


def get_user_selections():
    """Get all user selections before starting the analysis display."""
    # Display ASCII art welcome message
    with open(Path(__file__).parent / "static" / "welcome.txt", encoding="utf-8") as f:
        welcome_ascii = f.read()

    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgents: Multi-Agents LLM Financial Trading Framework - CLI[/bold green]\n\n"
    welcome_content += "[bold]Workflow Steps:[/bold]\n"
    welcome_content += "I. Analyst Team → II. Research Team → III. Trader → IV. Risk Management → V. Portfolio Management\n\n"
    welcome_content += (
        "[dim]Built by [Tauric Research](https://github.com/TauricResearch)[/dim]"
    )

    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="Welcome to TradingAgents",
        subtitle="Multi-Agents LLM Financial Trading Framework",
    )
    console.print(Align.center(welcome_box))
    console.print()
    console.print()

    # Fetch and display announcements (silent on failure)
    announcements = fetch_announcements()
    display_announcements(console, announcements)

    def create_question_box(title, prompt, default=None):
        box_content = f"[bold]{title}[/bold]\n"
        box_content += f"[dim]{prompt}[/dim]"
        if default:
            box_content += f"\n[dim]Default: {default}[/dim]"
        return Panel(box_content, border_style="blue", padding=(1, 2))

    def thinking_value_or_prompt(env_var, config_key, label, box_title, box_body, prompt_fn):
        """Return the env-configured reasoning/thinking value, or prompt for it."""
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
    if asset_type.value != "stock":
        console.print(f"[green]Detected asset type:[/green] {asset_type.value}")

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
    if os.environ.get("TRADINGAGENTS_OUTPUT_LANGUAGE"):
        output_language = DEFAULT_CONFIG["output_language"]
        console.print(f"[green]✓ Output language from environment:[/green] {output_language}")
    else:
        console.print(create_question_box("Step 3: Output Language",
            "Select the language for analyst reports and final decision"))
        output_language = ask_output_language()

    # Step 4: Select analysts
    console.print(create_question_box("Step 4: Analysts Team",
        "Select your LLM analyst agents for the analysis"))
    selected_analysts = select_analysts(asset_type)
    console.print(f"[green]Selected analysts:[/green] {', '.join(a.value for a in selected_analysts)}")

    # Step 5: Research depth
    depth_from_env = bool(os.environ.get("TRADINGAGENTS_MAX_DEBATE_ROUNDS")) and bool(
        os.environ.get("TRADINGAGENTS_MAX_RISK_ROUNDS")
    )
    if depth_from_env:
        selected_research_depth = DEFAULT_CONFIG["max_debate_rounds"]
        console.print(f"[green]✓ Research depth from environment:[/green] "
                      f"{DEFAULT_CONFIG['max_debate_rounds']} debate / "
                      f"{DEFAULT_CONFIG['max_risk_discuss_rounds']} risk rounds")
    else:
        console.print(create_question_box("Step 5: Research Depth",
            "Select your research depth level"))
        selected_research_depth = select_research_depth()

    # Step 6: LLM Provider
    provider_from_env = bool(os.environ.get("TRADINGAGENTS_LLM_PROVIDER"))
    if provider_from_env:
        selected_llm_provider = DEFAULT_CONFIG["llm_provider"].lower()
        backend_url = resolve_backend_url(selected_llm_provider, env_url=DEFAULT_CONFIG["backend_url"])
        console.print(f"[green]✓ LLM provider from environment:[/green] {selected_llm_provider}")
        console.print(f"[green]✓ Backend URL:[/green] {backend_url}")
        ensure_api_key(selected_llm_provider)
    else:
        console.print(create_question_box("Step 6: LLM Provider", "Select your LLM provider"))
        selected_llm_provider, backend_url = select_llm_provider()

        if selected_llm_provider == "qwen":
            selected_llm_provider, backend_url = ask_qwen_region()
        elif selected_llm_provider == "minimax":
            selected_llm_provider, backend_url = ask_minimax_region()
        elif selected_llm_provider == "glm":
            selected_llm_provider, backend_url = ask_glm_region()

        backend_url = resolve_backend_url(selected_llm_provider, backend_url,
                                          env_url=DEFAULT_CONFIG["backend_url"])

        if selected_llm_provider == "openai_compatible" and not backend_url:
            backend_url = prompt_openai_compatible_url()

        if selected_llm_provider == "ollama":
            confirm_ollama_endpoint(backend_url)

        ensure_api_key(selected_llm_provider)

    # Step 7: Thinking agents
    if os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM") or os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM"):
        selected_shallow_thinker = DEFAULT_CONFIG["quick_think_llm"]
        selected_deep_thinker = DEFAULT_CONFIG["deep_think_llm"]
        console.print(f"[green]✓ Thinking agents from environment:[/green] "
                      f"quick={selected_shallow_thinker}, deep={selected_deep_thinker}")
    else:
        console.print(create_question_box("Step 7: Thinking Agents",
            "Select your thinking agents for analysis"))
        selected_shallow_thinker = select_shallow_thinking_agent(selected_llm_provider)
        selected_deep_thinker = select_deep_thinking_agent(selected_llm_provider)

    # Step 8: Provider-specific reasoning/thinking configuration
    thinking_level = None
    reasoning_effort = None
    anthropic_effort = None

    provider_lower = selected_llm_provider.lower()
    if provider_from_env:
        thinking_level = DEFAULT_CONFIG["google_thinking_level"]
        reasoning_effort = DEFAULT_CONFIG["openai_reasoning_effort"]
        anthropic_effort = DEFAULT_CONFIG["anthropic_effort"]
    elif provider_lower == "google":
        thinking_level = thinking_value_or_prompt(
            "TRADINGAGENTS_GOOGLE_THINKING_LEVEL", "google_thinking_level",
            "Gemini thinking mode", "Step 8: Thinking Mode",
            "Configure Gemini thinking mode", ask_gemini_thinking_config)
    elif provider_lower == "openai":
        reasoning_effort = thinking_value_or_prompt(
            "TRADINGAGENTS_OPENAI_REASONING_EFFORT", "openai_reasoning_effort",
            "Reasoning effort", "Step 8: Reasoning Effort",
            "Configure OpenAI reasoning effort level", ask_openai_reasoning_effort)
    elif provider_lower == "anthropic":
        anthropic_effort = thinking_value_or_prompt(
            "TRADINGAGENTS_ANTHROPIC_EFFORT", "anthropic_effort",
            "Claude effort", "Step 8: Effort Level",
            "Configure Claude effort level", ask_anthropic_effort)

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


# ---------------------------------------------------------------------------
# Config assembly
# ---------------------------------------------------------------------------

def _build_run_config(selections: dict, checkpoint: bool | None) -> dict:
    """Assemble the run config from interactive selections, honoring env precedence."""
    config = DEFAULT_CONFIG.copy()

    if not os.environ.get("TRADINGAGENTS_MAX_DEBATE_ROUNDS"):
        config["max_debate_rounds"] = selections["research_depth"]
    if not os.environ.get("TRADINGAGENTS_MAX_RISK_ROUNDS"):
        config["max_risk_discuss_rounds"] = selections["research_depth"]

    config["quick_think_llm"] = selections["shallow_thinker"]
    config["deep_think_llm"] = selections["deep_thinker"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()
    config["google_thinking_level"] = selections.get("google_thinking_level")
    config["openai_reasoning_effort"] = selections.get("openai_reasoning_effort")
    config["anthropic_effort"] = selections.get("anthropic_effort")
    config["output_language"] = selections.get("output_language", "English")

    if checkpoint is not None:
        config["checkpoint_enabled"] = checkpoint

    return config


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

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
        console.print(Panel(Markdown(final_state["trader_investment_plan"]), title="Trader",
                            border_style="blue", padding=(1, 2)))

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
            console.print(Panel(Markdown(risk["judge_decision"]), title="Portfolio Manager",
                                border_style="blue", padding=(1, 2)))


# ---------------------------------------------------------------------------
# Main analysis runner
# ---------------------------------------------------------------------------

def run_analysis(checkpoint: bool | None = None):
    # ---- 1. User selections ----
    selections = get_user_selections()
    config = _build_run_config(selections, checkpoint)

    # ---- 2. Component setup ----
    stats_handler = StatsCallbackHandler()

    selected_set = {analyst.value for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in AgentStatusTracker.ANALYST_ORDER if a in selected_set]
    analyst_execution_plan = build_analyst_execution_plan(selected_analyst_keys)
    analyst_wall_time_tracker = AnalystWallTimeTracker(analyst_execution_plan)

    # Graph
    graph = TradingAgentsGraph(
        selected_analyst_keys,
        config=config,
        debug=True,
        callbacks=[stats_handler],
    )

    # Live display components (extracted from the former MessageBuffer / update_display)
    agent_tracker = AgentStatusTracker()
    message_store = MessageStore()
    report_builder = ReportBuilder()
    display_mgr = DisplayManager()

    agent_tracker.init_for_analysis(selected_analyst_keys)
    report_builder.init_for_analysis(selected_analyst_keys)

    # ---- 3. Start display ----
    start_time = time.time()
    layout = display_mgr.create_layout()

    results_dir = Path(config["results_dir"]) / selections["ticker"] / selections["analysis_date"]
    results_dir.mkdir(parents=True, exist_ok=True)
    report_dir = results_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_file = results_dir / "message_tool.log"
    log_file.touch(exist_ok=True)

    # ---- 4. Decorators for file logging ----
    def save_message_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, message_type, content = obj.messages[-1]
            content = content.replace("\n", " ")
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

    message_store.add_message = save_message_decorator(message_store, "add_message")
    message_store.add_tool_call = save_tool_call_decorator(message_store, "add_tool_call")
    report_builder.update_section = save_report_section_decorator(report_builder, "update_section")

    # ---- 5. Live display loop ----
    with Live(layout, refresh_per_second=4):
        # Initial display
        display_mgr.update_all(agent_tracker, message_store, report_builder,
                               stats_handler=stats_handler, start_time=start_time)

        message_store.add_message("System", f"Selected ticker: {selections['ticker']}")
        if selections["asset_type"] != "stock":
            message_store.add_message("System", f"Detected asset type: {selections['asset_type']}")
        message_store.add_message("System", f"Analysis date: {selections['analysis_date']}")
        message_store.add_message(
            "System",
            f"Selected analysts: {', '.join(analyst.value for analyst in selections['analysts'])}",
        )
        display_mgr.update_all(agent_tracker, message_store, report_builder,
                               stats_handler=stats_handler, start_time=start_time)

        # Mark first analyst as in_progress
        first_analyst = get_initial_analyst_node(analyst_execution_plan)
        agent_tracker.update_status(first_analyst, "in_progress")
        analyst_wall_time_tracker.mark_started(selected_analyst_keys[0])
        display_mgr.update_all(agent_tracker, message_store, report_builder,
                               stats_handler=stats_handler, start_time=start_time)

        # Resolve instrument context once
        instrument_context = graph.resolve_instrument_context(
            selections["ticker"], selections["asset_type"])
        init_agent_state = graph.propagator.create_initial_state(
            selections["ticker"],
            selections["analysis_date"],
            asset_type=selections["asset_type"],
            instrument_context=instrument_context,
        )
        args = graph.propagator.get_graph_args(callbacks=[stats_handler])

        # Stream the analysis
        trace = []
        for chunk in graph.graph.stream(init_agent_state, **args):
            # Process messages with dedup
            for message in chunk.get("messages", []):
                msg_id = getattr(message, "id", None)
                if msg_id is not None:
                    if message_store.is_duplicate(msg_id):
                        continue
                    message_store.mark_processed(msg_id)

                msg_type, content = classify_message_type(message)
                if content and content.strip():
                    message_store.add_message(msg_type, content)

                if hasattr(message, "tool_calls") and message.tool_calls:
                    for tool_call in message.tool_calls:
                        if isinstance(tool_call, dict):
                            message_store.add_tool_call(tool_call["name"], tool_call["args"])
                        else:
                            message_store.add_tool_call(tool_call.name, tool_call.args)

            # Analyst status updates
            agent_tracker.update_from_analyst_stream(
                chunk, report_builder,
                wall_time_tracker=analyst_wall_time_tracker,
            )

            # Research Team — handle investment debate state
            if chunk.get("investment_debate_state"):
                debate_state = chunk["investment_debate_state"]
                bull_hist = debate_state.get("bull_history", "").strip()
                bear_hist = debate_state.get("bear_history", "").strip()
                judge = debate_state.get("judge_decision", "").strip()

                if bull_hist or bear_hist:
                    agent_tracker.mark_research_team_in_progress()
                if bull_hist:
                    report_builder.update_section(
                        "investment_plan", f"### Bull Researcher Analysis\n{bull_hist}")
                if bear_hist:
                    report_builder.update_section(
                        "investment_plan", f"### Bear Researcher Analysis\n{bear_hist}")
                if judge:
                    report_builder.update_section(
                        "investment_plan", f"### Research Manager Decision\n{judge}")
                    agent_tracker.update_status("Bull Researcher", "completed")
                    agent_tracker.update_status("Bear Researcher", "completed")
                    agent_tracker.update_status("Research Manager", "completed")
                    agent_tracker.update_status("Trader", "in_progress")

            # Trading Team
            if chunk.get("trader_investment_plan"):
                report_builder.update_section("trader_investment_plan", chunk["trader_investment_plan"])
                if agent_tracker.agent_status.get("Trader") != "completed":
                    agent_tracker.update_status("Trader", "completed")
                    agent_tracker.update_status("Aggressive Analyst", "in_progress")

            # Risk Management Team
            if chunk.get("risk_debate_state"):
                risk_state = chunk["risk_debate_state"]
                agg_hist = risk_state.get("aggressive_history", "").strip()
                con_hist = risk_state.get("conservative_history", "").strip()
                neu_hist = risk_state.get("neutral_history", "").strip()
                judge = risk_state.get("judge_decision", "").strip()

                if agg_hist:
                    if agent_tracker.agent_status.get("Aggressive Analyst") != "completed":
                        agent_tracker.update_status("Aggressive Analyst", "in_progress")
                    report_builder.update_section(
                        "final_trade_decision", f"### Aggressive Analyst Analysis\n{agg_hist}")
                if con_hist:
                    if agent_tracker.agent_status.get("Conservative Analyst") != "completed":
                        agent_tracker.update_status("Conservative Analyst", "in_progress")
                    report_builder.update_section(
                        "final_trade_decision", f"### Conservative Analyst Analysis\n{con_hist}")
                if neu_hist:
                    if agent_tracker.agent_status.get("Neutral Analyst") != "completed":
                        agent_tracker.update_status("Neutral Analyst", "in_progress")
                    report_builder.update_section(
                        "final_trade_decision", f"### Neutral Analyst Analysis\n{neu_hist}")
                if judge and agent_tracker.agent_status.get("Portfolio Manager") != "completed":
                    agent_tracker.update_status("Portfolio Manager", "in_progress")
                    report_builder.update_section(
                        "final_trade_decision", f"### Portfolio Manager Decision\n{judge}")
                    agent_tracker.update_status("Aggressive Analyst", "completed")
                    agent_tracker.update_status("Conservative Analyst", "completed")
                    agent_tracker.update_status("Neutral Analyst", "completed")
                    agent_tracker.update_status("Portfolio Manager", "completed")

            # Refresh display
            display_mgr.update_all(agent_tracker, message_store, report_builder,
                                   stats_handler=stats_handler, start_time=start_time)
            trace.append(chunk)

        # ---- 6. Post-stream: merge state ----
        final_state = {}
        for chunk in trace:
            final_state.update(chunk)

        agent_tracker.set_all_completed()

        message_store.add_message("System", f"Completed analysis for {selections['analysis_date']}")
        message_store.add_message("System", analyst_wall_time_tracker.format_summary())

        for section in report_builder.report_sections:
            if section in final_state:
                report_builder.update_section(section, final_state[section])

        display_mgr.update_all(agent_tracker, message_store, report_builder,
                               stats_handler=stats_handler, start_time=start_time)

    # ---- 7. Post-analysis prompts (outside Live) ----
    console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")
    console.print(f"[dim]{analyst_wall_time_tracker.format_summary()}[/dim]")

    # Prompt to save report
    save_choice = typer.prompt("Save report?", default="Y").strip().upper()
    if save_choice in ("Y", "YES", ""):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = Path.cwd() / "reports" / f"{selections['ticker']}_{timestamp}"
        save_path_str = typer.prompt("Save path (press Enter for default)", default=str(default_path)).strip()
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


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

@app.command()
def analyze(
    checkpoint: bool | None = typer.Option(
        None,
        "--checkpoint/--no-checkpoint",
        help="Enable/disable checkpoint-resume. Omit to honor TRADINGAGENTS_CHECKPOINT_ENABLED.",
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
    run_analysis(checkpoint=checkpoint)


if __name__ == "__main__":
    app()
