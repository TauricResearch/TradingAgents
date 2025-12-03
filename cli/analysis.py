import datetime
from pathlib import Path
from functools import wraps
from typing import List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.align import Align

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.dataflows.config import get_config

from cli.state import message_buffer
from cli.models import AnalystType
from cli.display import (
    create_layout,
    update_display,
    display_complete_report,
    update_research_team_status,
    extract_content_string,
    create_question_box,
    console,
)
from cli.utils import (
    select_analysts,
    select_research_depth,
    select_shallow_thinking_agent,
    select_deep_thinking_agent,
    select_llm_provider,
    loading,
)


def get_ticker() -> str:
    return typer.prompt("", default="SPY")


def get_analysis_date() -> str:
    while True:
        date_str = typer.prompt(
            "", default=datetime.datetime.now().strftime("%Y-%m-%d")
        )
        try:
            analysis_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            if analysis_date.date() > datetime.datetime.now().date():
                console.print("[red]Error: Analysis date cannot be in the future[/red]")
                continue
            return date_str
        except ValueError:
            console.print(
                "[red]Error: Invalid date format. Please use YYYY-MM-DD[/red]"
            )


def get_user_selections() -> dict:
    with open("./cli/static/welcome.txt", "r") as f:
        welcome_ascii = f.read()

    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgents: Multi-Agents LLM Financial Trading Framework - CLI[/bold green]\n\n"
    welcome_content += "[bold]Workflow Steps:[/bold]\n"
    welcome_content += "I. Analyst Team -> II. Research Team -> III. Trader -> IV. Risk Management -> V. Portfolio Management\n\n"
    welcome_content += "[dim]Built by Tauric Research (https://github.com/TauricResearch)[/dim]"

    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="Welcome to TradingAgents",
        subtitle="Multi-Agents LLM Financial Trading Framework",
    )
    console.print(Align.center(welcome_box))
    console.print()

    console.print(
        create_question_box(
            "Step 1: Ticker Symbol", "Enter the ticker symbol to analyze", "SPY"
        )
    )
    selected_ticker = get_ticker()

    default_date = datetime.datetime.now().strftime("%Y-%m-%d")
    console.print(
        create_question_box(
            "Step 2: Analysis Date",
            "Enter the analysis date (YYYY-MM-DD)",
            default_date,
        )
    )
    analysis_date = get_analysis_date()

    console.print(
        create_question_box(
            "Step 3: Analysts Team", "Select your LLM analyst agents for the analysis"
        )
    )
    selected_analysts = select_analysts()
    console.print(
        f"[green]Selected analysts:[/green] {', '.join(analyst.value for analyst in selected_analysts)}"
    )

    console.print(
        create_question_box(
            "Step 4: Research Depth", "Select your research depth level"
        )
    )
    selected_research_depth = select_research_depth()

    console.print(
        create_question_box(
            "Step 5: OpenAI backend", "Select which service to talk to"
        )
    )
    selected_llm_provider, backend_url = select_llm_provider()

    console.print(
        create_question_box(
            "Step 6: Thinking Agents", "Select your thinking agents for analysis"
        )
    )
    selected_shallow_thinker = select_shallow_thinking_agent(selected_llm_provider)
    selected_deep_thinker = select_deep_thinking_agent(selected_llm_provider)

    return {
        "ticker": selected_ticker,
        "analysis_date": analysis_date,
        "analysts": selected_analysts,
        "research_depth": selected_research_depth,
        "llm_provider": selected_llm_provider.lower(),
        "backend_url": backend_url,
        "shallow_thinker": selected_shallow_thinker,
        "deep_thinker": selected_deep_thinker,
    }


def process_chunk_for_display(chunk: dict, selected_analysts: List[AnalystType]) -> None:
    if "market_report" in chunk and chunk["market_report"]:
        message_buffer.update_report_section("market_report", chunk["market_report"])
        message_buffer.update_agent_status("Market Analyst", "completed")
        if AnalystType.SOCIAL in selected_analysts:
            message_buffer.update_agent_status("Social Analyst", "in_progress")

    if "sentiment_report" in chunk and chunk["sentiment_report"]:
        message_buffer.update_report_section("sentiment_report", chunk["sentiment_report"])
        message_buffer.update_agent_status("Social Analyst", "completed")
        if AnalystType.NEWS in selected_analysts:
            message_buffer.update_agent_status("News Analyst", "in_progress")

    if "news_report" in chunk and chunk["news_report"]:
        message_buffer.update_report_section("news_report", chunk["news_report"])
        message_buffer.update_agent_status("News Analyst", "completed")
        if AnalystType.FUNDAMENTALS in selected_analysts:
            message_buffer.update_agent_status("Fundamentals Analyst", "in_progress")

    if "fundamentals_report" in chunk and chunk["fundamentals_report"]:
        message_buffer.update_report_section("fundamentals_report", chunk["fundamentals_report"])
        message_buffer.update_agent_status("Fundamentals Analyst", "completed")
        update_research_team_status("in_progress")

    if "investment_debate_state" in chunk and chunk["investment_debate_state"]:
        debate_state = chunk["investment_debate_state"]

        if "bull_history" in debate_state and debate_state["bull_history"]:
            update_research_team_status("in_progress")
            bull_responses = debate_state["bull_history"].split("\n")
            latest_bull = bull_responses[-1] if bull_responses else ""
            if latest_bull:
                message_buffer.add_message("Reasoning", latest_bull)
                message_buffer.update_report_section(
                    "investment_plan",
                    f"### Bull Researcher Analysis\n{latest_bull}",
                )

        if "bear_history" in debate_state and debate_state["bear_history"]:
            update_research_team_status("in_progress")
            bear_responses = debate_state["bear_history"].split("\n")
            latest_bear = bear_responses[-1] if bear_responses else ""
            if latest_bear:
                message_buffer.add_message("Reasoning", latest_bear)
                message_buffer.update_report_section(
                    "investment_plan",
                    f"{message_buffer.report_sections['investment_plan']}\n\n### Bear Researcher Analysis\n{latest_bear}",
                )

        if "judge_decision" in debate_state and debate_state["judge_decision"]:
            update_research_team_status("in_progress")
            message_buffer.add_message(
                "Reasoning",
                f"Research Manager: {debate_state['judge_decision']}",
            )
            message_buffer.update_report_section(
                "investment_plan",
                f"{message_buffer.report_sections['investment_plan']}\n\n### Research Manager Decision\n{debate_state['judge_decision']}",
            )
            update_research_team_status("completed")
            message_buffer.update_agent_status("Risky Analyst", "in_progress")

    if "trader_investment_plan" in chunk and chunk["trader_investment_plan"]:
        message_buffer.update_report_section("trader_investment_plan", chunk["trader_investment_plan"])
        message_buffer.update_agent_status("Risky Analyst", "in_progress")

    if "risk_debate_state" in chunk and chunk["risk_debate_state"]:
        risk_state = chunk["risk_debate_state"]

        if "current_risky_response" in risk_state and risk_state["current_risky_response"]:
            message_buffer.update_agent_status("Risky Analyst", "in_progress")
            message_buffer.add_message(
                "Reasoning",
                f"Risky Analyst: {risk_state['current_risky_response']}",
            )
            message_buffer.update_report_section(
                "final_trade_decision",
                f"### Risky Analyst Analysis\n{risk_state['current_risky_response']}",
            )

        if "current_safe_response" in risk_state and risk_state["current_safe_response"]:
            message_buffer.update_agent_status("Safe Analyst", "in_progress")
            message_buffer.add_message(
                "Reasoning",
                f"Safe Analyst: {risk_state['current_safe_response']}",
            )
            message_buffer.update_report_section(
                "final_trade_decision",
                f"### Safe Analyst Analysis\n{risk_state['current_safe_response']}",
            )

        if "current_neutral_response" in risk_state and risk_state["current_neutral_response"]:
            message_buffer.update_agent_status("Neutral Analyst", "in_progress")
            message_buffer.add_message(
                "Reasoning",
                f"Neutral Analyst: {risk_state['current_neutral_response']}",
            )
            message_buffer.update_report_section(
                "final_trade_decision",
                f"### Neutral Analyst Analysis\n{risk_state['current_neutral_response']}",
            )

        if "judge_decision" in risk_state and risk_state["judge_decision"]:
            message_buffer.update_agent_status("Portfolio Manager", "in_progress")
            message_buffer.add_message(
                "Reasoning",
                f"Portfolio Manager: {risk_state['judge_decision']}",
            )
            message_buffer.update_report_section(
                "final_trade_decision",
                f"### Portfolio Manager Decision\n{risk_state['judge_decision']}",
            )
            message_buffer.update_agent_status("Risky Analyst", "completed")
            message_buffer.update_agent_status("Safe Analyst", "completed")
            message_buffer.update_agent_status("Neutral Analyst", "completed")
            message_buffer.update_agent_status("Portfolio Manager", "completed")


def setup_logging_decorators(report_dir, log_file) -> tuple:
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
            timestamp, tool_name, tool_args = obj.tool_calls[-1]
            args_str = ", ".join(f"{k}={v}" for k, v in tool_args.items())
            with open(log_file, "a") as f:
                f.write(f"{timestamp} [Tool Call] {tool_name}({args_str})\n")
        return wrapper

    def save_report_section_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(section_name, content):
            func(section_name, content)
            if section_name in obj.report_sections and obj.report_sections[section_name] is not None:
                section_content = obj.report_sections[section_name]
                if section_content:
                    file_name = f"{section_name}.md"
                    with open(report_dir / file_name, "w") as f:
                        f.write(section_content)
        return wrapper

    return save_message_decorator, save_tool_call_decorator, save_report_section_decorator


def run_analysis_for_ticker(ticker: str, config: dict) -> None:
    analysis_date = datetime.datetime.now().strftime("%Y-%m-%d")

    console.print(
        create_question_box(
            "Analysts Team",
            "Select your LLM analyst agents for the analysis"
        )
    )
    selected_analysts = select_analysts()
    console.print(
        f"[green]Selected analysts:[/green] {', '.join(analyst.value for analyst in selected_analysts)}"
    )

    console.print(
        create_question_box(
            "Research Depth",
            "Select your research depth level"
        )
    )
    selected_research_depth = select_research_depth()

    console.print(
        create_question_box(
            "Deep-Thinking Model",
            "Select the model for deep analysis"
        )
    )
    llm_provider = config.get("llm_provider", "openai")
    selected_deep_thinker = select_deep_thinking_agent(llm_provider.capitalize())

    config["max_debate_rounds"] = selected_research_depth
    config["max_risk_discuss_rounds"] = selected_research_depth
    config["deep_think_llm"] = selected_deep_thinker

    _run_analysis_with_config(ticker, analysis_date, selected_analysts, config)


def run_analysis() -> None:
    selections = get_user_selections()

    config = get_config()
    config["max_debate_rounds"] = selections["research_depth"]
    config["max_risk_discuss_rounds"] = selections["research_depth"]
    config["quick_think_llm"] = selections["shallow_thinker"]
    config["deep_think_llm"] = selections["deep_thinker"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()

    _run_analysis_with_config(
        selections["ticker"],
        selections["analysis_date"],
        selections["analysts"],
        config
    )


def _run_analysis_with_config(ticker: str, analysis_date: str, selected_analysts: List[AnalystType], config: dict) -> None:
    with loading("Initializing trading agents...", show_elapsed=True):
        graph = TradingAgentsGraph(
            [analyst.value for analyst in selected_analysts], config=config, debug=True
        )

    results_dir = Path(config["results_dir"]) / ticker / analysis_date
    results_dir.mkdir(parents=True, exist_ok=True)
    report_dir = results_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_file = results_dir / "message_tool.log"
    log_file.touch(exist_ok=True)

    save_message_decorator, save_tool_call_decorator, save_report_section_decorator = \
        setup_logging_decorators(report_dir, log_file)

    message_buffer.add_message = save_message_decorator(message_buffer, "add_message")
    message_buffer.add_tool_call = save_tool_call_decorator(message_buffer, "add_tool_call")
    message_buffer.update_report_section = save_report_section_decorator(message_buffer, "update_report_section")

    layout = create_layout()

    with Live(layout, refresh_per_second=4):
        update_display(layout)

        message_buffer.add_message("System", f"Selected ticker: {ticker}")
        message_buffer.add_message("System", f"Analysis date: {analysis_date}")
        message_buffer.add_message(
            "System",
            f"Selected analysts: {', '.join(analyst.value for analyst in selected_analysts)}",
        )
        update_display(layout)

        for agent in message_buffer.agent_status:
            message_buffer.update_agent_status(agent, "pending")

        for section in message_buffer.report_sections:
            message_buffer.report_sections[section] = None
        message_buffer.current_report = None
        message_buffer.final_report = None

        first_analyst = f"{selected_analysts[0].value.capitalize()} Analyst"
        message_buffer.update_agent_status(first_analyst, "in_progress")
        update_display(layout)

        spinner_text = f"Analyzing {ticker} on {analysis_date}..."
        update_display(layout, spinner_text)

        init_agent_state = graph.propagator.create_initial_state(ticker, analysis_date)
        args = graph.propagator.get_graph_args()

        trace = []
        for chunk in graph.graph.stream(init_agent_state, **args):
            if len(chunk["messages"]) > 0:
                last_message = chunk["messages"][-1]

                if hasattr(last_message, "content"):
                    content = extract_content_string(last_message.content)
                    msg_type = "Reasoning"
                else:
                    content = str(last_message)
                    msg_type = "System"

                message_buffer.add_message(msg_type, content)

                if hasattr(last_message, "tool_calls"):
                    for tool_call in last_message.tool_calls:
                        if isinstance(tool_call, dict):
                            message_buffer.add_tool_call(tool_call["name"], tool_call["args"])
                        else:
                            message_buffer.add_tool_call(tool_call.name, tool_call.args)

                process_chunk_for_display(chunk, selected_analysts)
                update_display(layout)

            trace.append(chunk)

        final_state = trace[-1]
        decision = graph.process_signal(final_state["final_trade_decision"])

        for agent in message_buffer.agent_status:
            message_buffer.update_agent_status(agent, "completed")

        message_buffer.add_message("Analysis", f"Completed analysis for {analysis_date}")

        for section in message_buffer.report_sections.keys():
            if section in final_state:
                message_buffer.update_report_section(section, final_state[section])

        display_complete_report(final_state)
        update_display(layout)
