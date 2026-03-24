from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from analyst_access.run import (
    StageTraceCallbackHandler,
    json_dump,
    reset_messages,
    run_direct_stage,
    run_tool_backed_stage,
    stringify_content,
    write_markdown,
)
from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.trader.trader import create_trader
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.trading_graph import TradingAgentsGraph


AGENT_SPECS: Dict[str, Dict[str, Any]] = {
    "market_analyst": {
        "display_name": "Market Analyst",
        "stage_slug": "01_market_analyst",
        "kind": "tool_analyst",
        "llm": "quick",
        "required_data": [
            "OHLCV price history for the ticker",
            "technical indicators such as moving averages, MACD, RSI, Bollinger bands, ATR, and VWMA",
            "enough recent market data to support a directional market view",
        ],
        "prerequisites": [],
        "context_fields": ["market_report"],
        "goal_hint": "Focus on market structure, momentum, volatility, and technical setup.",
    },
    "social_media_analyst": {
        "display_name": "Social Media Analyst",
        "stage_slug": "02_social_media_analyst",
        "kind": "tool_analyst",
        "llm": "quick",
        "required_data": [
            "recent company-specific news and public discussion proxies",
            "enough recent articles to infer sentiment and narrative pressure",
        ],
        "prerequisites": [],
        "context_fields": ["sentiment_report"],
        "goal_hint": "Focus on sentiment, narrative, public mood, and recent company discussion.",
    },
    "news_analyst": {
        "display_name": "News Analyst",
        "stage_slug": "03_news_analyst",
        "kind": "tool_analyst",
        "llm": "quick",
        "required_data": [
            "company-specific recent news",
            "global and macro market news over the recent lookback window",
            "enough macro context to explain possible impact on the ticker",
        ],
        "prerequisites": [],
        "context_fields": ["news_report"],
        "goal_hint": "Focus on macro, catalysts, geopolitics, policy, and news impact.",
    },
    "fundamentals_analyst": {
        "display_name": "Fundamentals Analyst",
        "stage_slug": "04_fundamentals_analyst",
        "kind": "tool_analyst",
        "llm": "quick",
        "required_data": [
            "company profile and high-level fundamentals",
            "income statement data",
            "balance sheet data",
            "cash flow statement data",
        ],
        "prerequisites": [],
        "context_fields": ["fundamentals_report"],
        "goal_hint": "Focus on valuation, quality, growth, solvency, profitability, and cash generation.",
    },
    "bull_researcher": {
        "display_name": "Bull Researcher",
        "stage_slug": "05_bull_researcher",
        "kind": "derived",
        "llm": "quick",
        "required_data": [
            "market report",
            "sentiment report",
            "news report",
            "fundamentals report",
            "optionally prior debate context",
        ],
        "prerequisites": [
            "market_analyst",
            "social_media_analyst",
            "news_analyst",
            "fundamentals_analyst",
        ],
        "context_fields": [
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "investment_debate_state",
        ],
        "goal_hint": "Build the strongest bullish case and address downside concerns.",
    },
    "bear_researcher": {
        "display_name": "Bear Researcher",
        "stage_slug": "06_bear_researcher",
        "kind": "derived",
        "llm": "quick",
        "required_data": [
            "market report",
            "sentiment report",
            "news report",
            "fundamentals report",
            "a prior bullish argument to rebut",
        ],
        "prerequisites": [
            "market_analyst",
            "social_media_analyst",
            "news_analyst",
            "fundamentals_analyst",
            "bull_researcher",
        ],
        "context_fields": [
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "investment_debate_state",
        ],
        "goal_hint": "Build the strongest bearish case and rebut bullish assumptions.",
    },
    "research_manager": {
        "display_name": "Research Manager",
        "stage_slug": "07_research_manager",
        "kind": "derived",
        "llm": "deep",
        "required_data": [
            "bull and bear debate history",
            "analyst reports from market, sentiment, news, and fundamentals",
        ],
        "prerequisites": [
            "market_analyst",
            "social_media_analyst",
            "news_analyst",
            "fundamentals_analyst",
            "bull_researcher",
            "bear_researcher",
        ],
        "context_fields": ["investment_debate_state", "investment_plan"],
        "goal_hint": "Synthesize the debate into a clear investment plan.",
    },
    "trader": {
        "display_name": "Trader",
        "stage_slug": "08_trader",
        "kind": "derived",
        "llm": "quick",
        "required_data": [
            "investment plan from the research manager",
            "underlying analyst reports used to justify execution",
        ],
        "prerequisites": ["research_manager"],
        "context_fields": ["investment_plan", "trader_investment_plan"],
        "goal_hint": "Translate research into a concrete trading action.",
    },
    "aggressive_risk_analyst": {
        "display_name": "Aggressive Analyst",
        "stage_slug": "09_aggressive_risk_analyst",
        "kind": "derived",
        "llm": "quick",
        "required_data": [
            "trader plan",
            "market, sentiment, news, and fundamentals reports",
        ],
        "prerequisites": ["trader"],
        "context_fields": ["trader_investment_plan", "risk_debate_state"],
        "goal_hint": "Argue for upside, convexity, and tolerated risk.",
    },
    "conservative_risk_analyst": {
        "display_name": "Conservative Analyst",
        "stage_slug": "10_conservative_risk_analyst",
        "kind": "derived",
        "llm": "quick",
        "required_data": [
            "trader plan",
            "market, sentiment, news, and fundamentals reports",
            "aggressive risk argument to challenge",
        ],
        "prerequisites": ["aggressive_risk_analyst"],
        "context_fields": ["trader_investment_plan", "risk_debate_state"],
        "goal_hint": "Argue for capital preservation and downside protection.",
    },
    "neutral_risk_analyst": {
        "display_name": "Neutral Analyst",
        "stage_slug": "11_neutral_risk_analyst",
        "kind": "derived",
        "llm": "quick",
        "required_data": [
            "trader plan",
            "market, sentiment, news, and fundamentals reports",
            "aggressive and conservative arguments to balance",
        ],
        "prerequisites": ["conservative_risk_analyst"],
        "context_fields": ["trader_investment_plan", "risk_debate_state"],
        "goal_hint": "Balance upside and risk into a realistic position view.",
    },
    "portfolio_manager": {
        "display_name": "Portfolio Manager",
        "stage_slug": "12_portfolio_manager",
        "kind": "derived",
        "llm": "deep",
        "required_data": [
            "full risk debate history",
            "trader plan",
            "supporting upstream analyst reports",
        ],
        "prerequisites": ["neutral_risk_analyst"],
        "context_fields": ["risk_debate_state", "final_trade_decision"],
        "goal_hint": "Deliver the final actionable rating and portfolio action plan.",
    },
}


STAGE_ORDER = [
    "market_analyst",
    "social_media_analyst",
    "news_analyst",
    "fundamentals_analyst",
    "bull_researcher",
    "bear_researcher",
    "research_manager",
    "trader",
    "aggressive_risk_analyst",
    "conservative_risk_analyst",
    "neutral_risk_analyst",
    "portfolio_manager",
]


def build_config(
    quick_model: str | None = None,
    deep_model: str | None = None,
    reasoning_effort: str | None = None,
) -> Dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "openai"
    if quick_model:
        config["quick_think_llm"] = quick_model
    if deep_model:
        config["deep_think_llm"] = deep_model
    if reasoning_effort:
        config["openai_reasoning_effort"] = reasoning_effort
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    return config


def list_agents() -> List[Dict[str, Any]]:
    return [
        {
            "agent_key": key,
            "display_name": spec["display_name"],
            "required_data": spec["required_data"],
            "prerequisites": spec["prerequisites"],
            "goal_hint": spec["goal_hint"],
        }
        for key, spec in AGENT_SPECS.items()
    ]


def describe_agent(agent_key: str) -> Dict[str, Any]:
    if agent_key not in AGENT_SPECS:
        raise KeyError(f"Unknown agent_key: {agent_key}")
    return {"agent_key": agent_key, **AGENT_SPECS[agent_key]}


def execution_plan(agent_key: str) -> List[str]:
    if agent_key not in AGENT_SPECS:
        raise KeyError(f"Unknown agent_key: {agent_key}")

    needed: set[str] = set()

    def collect(current_key: str) -> None:
        if current_key in needed:
            return
        for prerequisite in AGENT_SPECS[current_key]["prerequisites"]:
            collect(prerequisite)
        needed.add(current_key)

    collect(agent_key)
    return [stage_key for stage_key in STAGE_ORDER if stage_key in needed]


def _workbench_message(
    ticker: str,
    trade_date: str,
    agent_display_name: str,
    user_request: str,
) -> HumanMessage:
    return HumanMessage(
        content=(
            f"You are working on ticker `{ticker}` for trade date `{trade_date}`.\n"
            f"The active specialist is `{agent_display_name}`.\n"
            f"User request: {user_request}\n\n"
            "Gather sufficient relevant data before concluding. If important data is missing or unavailable, "
            "say exactly what is missing and why it matters."
        )
    )


def _build_nodes(graph: TradingAgentsGraph) -> Dict[str, Any]:
    return {
        "market_analyst": create_market_analyst(graph.quick_thinking_llm),
        "social_media_analyst": create_social_media_analyst(graph.quick_thinking_llm),
        "news_analyst": create_news_analyst(graph.quick_thinking_llm),
        "fundamentals_analyst": create_fundamentals_analyst(graph.quick_thinking_llm),
        "bull_researcher": create_bull_researcher(graph.quick_thinking_llm, graph.bull_memory),
        "bear_researcher": create_bear_researcher(graph.quick_thinking_llm, graph.bear_memory),
        "research_manager": create_research_manager(graph.deep_thinking_llm, graph.invest_judge_memory),
        "trader": create_trader(graph.quick_thinking_llm, graph.trader_memory),
        "aggressive_risk_analyst": create_aggressive_debator(graph.quick_thinking_llm),
        "conservative_risk_analyst": create_conservative_debator(graph.quick_thinking_llm),
        "neutral_risk_analyst": create_neutral_debator(graph.quick_thinking_llm),
        "portfolio_manager": create_portfolio_manager(graph.deep_thinking_llm, graph.portfolio_manager_memory),
    }


def _selected_context(agent_key: str, state: Dict[str, Any]) -> Dict[str, Any]:
    fields = AGENT_SPECS[agent_key]["context_fields"]
    return {field: state.get(field, "") for field in fields}


def _followup_prompt(agent_key: str, ticker: str, trade_date: str, user_request: str, state: Dict[str, Any]) -> List[Any]:
    spec = AGENT_SPECS[agent_key]
    context_bundle = _selected_context(agent_key, state)
    context_text = json.dumps(context_bundle, indent=2, ensure_ascii=False, default=str)
    required_data_text = "\n".join(f"- {item}" for item in spec["required_data"])

    system = (
        f"You are the {spec['display_name']} for ticker `{ticker}` on trade date `{trade_date}`.\n"
        f"Your domain focus: {spec['goal_hint']}\n\n"
        "Use the provided evidence bundle to answer the user's request.\n"
        "If the available evidence is insufficient, include a section starting with `MISSING DATA:` and list exactly what else is needed.\n"
        "Be concrete, analytical, and explicit about what data supports each conclusion."
    )

    human = (
        f"Required data for this agent:\n{required_data_text}\n\n"
        f"User request:\n{user_request}\n\n"
        f"Available evidence bundle:\n{context_text}"
    )

    return [("system", system), ("human", human)]


def _run_followup(
    agent_key: str,
    graph: TradingAgentsGraph,
    tracer: StageTraceCallbackHandler,
    state: Dict[str, Any],
    ticker: str,
    trade_date: str,
    user_request: str,
    output_dir: Path,
) -> str:
    spec = AGENT_SPECS[agent_key]
    llm = graph.quick_thinking_llm if spec["llm"] == "quick" else graph.deep_thinking_llm

    stage_name = f"{spec['display_name']} Follow-Up"
    tracer.set_stage(stage_name)
    messages = _followup_prompt(agent_key, ticker, trade_date, user_request, state)
    result = llm.invoke(messages)
    tracer.clear_stage()

    followup_dir = output_dir / "selected_agent_followup"
    followup_dir.mkdir(parents=True, exist_ok=True)
    write_markdown(followup_dir / "answer.md", stringify_content(result.content))
    json_dump(
        followup_dir / "context_bundle.json",
        {
            "agent_key": agent_key,
            "display_name": spec["display_name"],
            "required_data": spec["required_data"],
            "user_request": user_request,
            "context_bundle": _selected_context(agent_key, state),
        },
    )
    records = tracer.get_stage_records(stage_name)
    json_dump(followup_dir / "llm_calls.json", records)
    return stringify_content(result.content)


def _ensure_state_message(state: Dict[str, Any], ticker: str, trade_date: str, agent_key: str, user_request: str) -> None:
    state["messages"] = [
        _workbench_message(ticker, trade_date, AGENT_SPECS[agent_key]["display_name"], user_request)
    ]


def run_agent_request(
    ticker: str,
    trade_date: str,
    agent_key: str,
    user_request: str,
    output_root: str = "analyst_access_sessions",
    quick_model: str | None = None,
    deep_model: str | None = None,
    reasoning_effort: str | None = None,
) -> Dict[str, Any]:
    load_dotenv()

    if agent_key not in AGENT_SPECS:
        raise KeyError(f"Unknown agent_key: {agent_key}")

    config = build_config(
        quick_model=quick_model,
        deep_model=deep_model,
        reasoning_effort=reasoning_effort,
    )
    tracer = StageTraceCallbackHandler()
    graph = TradingAgentsGraph(
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config=config,
        callbacks=[tracer],
    )
    nodes = _build_nodes(graph)
    state = graph.propagator.create_initial_state(ticker.upper(), trade_date)

    run_root = (
        Path(output_root)
        / ticker.upper()
        / trade_date
        / agent_key
        / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    run_root.mkdir(parents=True, exist_ok=True)
    json_dump(run_root / "config.json", config)
    json_dump(run_root / "agent_spec.json", describe_agent(agent_key))

    plan = execution_plan(agent_key)

    for stage_key in plan:
        _ensure_state_message(state, ticker.upper(), trade_date, stage_key, user_request)

        if stage_key == "market_analyst":
            run_tool_backed_stage(
                "Market Analyst",
                AGENT_SPECS[stage_key]["stage_slug"],
                nodes[stage_key],
                state,
                "market_report",
                tracer,
                run_root,
            )
            if agent_key != stage_key:
                reset_messages(state)
        elif stage_key == "social_media_analyst":
            run_tool_backed_stage(
                "Social Media Analyst",
                AGENT_SPECS[stage_key]["stage_slug"],
                nodes[stage_key],
                state,
                "sentiment_report",
                tracer,
                run_root,
            )
            if agent_key != stage_key:
                reset_messages(state)
        elif stage_key == "news_analyst":
            run_tool_backed_stage(
                "News Analyst",
                AGENT_SPECS[stage_key]["stage_slug"],
                nodes[stage_key],
                state,
                "news_report",
                tracer,
                run_root,
            )
            if agent_key != stage_key:
                reset_messages(state)
        elif stage_key == "fundamentals_analyst":
            run_tool_backed_stage(
                "Fundamentals Analyst",
                AGENT_SPECS[stage_key]["stage_slug"],
                nodes[stage_key],
                state,
                "fundamentals_report",
                tracer,
                run_root,
            )
            if agent_key != stage_key:
                reset_messages(state)
        elif stage_key == "bull_researcher":
            run_direct_stage(
                "Bull Researcher",
                AGENT_SPECS[stage_key]["stage_slug"],
                nodes[stage_key],
                state,
                "investment_debate_state",
                tracer,
                run_root,
            )
        elif stage_key == "bear_researcher":
            run_direct_stage(
                "Bear Researcher",
                AGENT_SPECS[stage_key]["stage_slug"],
                nodes[stage_key],
                state,
                "investment_debate_state",
                tracer,
                run_root,
            )
        elif stage_key == "research_manager":
            run_direct_stage(
                "Research Manager",
                AGENT_SPECS[stage_key]["stage_slug"],
                nodes[stage_key],
                state,
                "investment_plan",
                tracer,
                run_root,
            )
        elif stage_key == "trader":
            run_direct_stage(
                "Trader",
                AGENT_SPECS[stage_key]["stage_slug"],
                nodes[stage_key],
                state,
                "trader_investment_plan",
                tracer,
                run_root,
            )
        elif stage_key == "aggressive_risk_analyst":
            run_direct_stage(
                "Aggressive Analyst",
                AGENT_SPECS[stage_key]["stage_slug"],
                nodes[stage_key],
                state,
                "risk_debate_state",
                tracer,
                run_root,
            )
        elif stage_key == "conservative_risk_analyst":
            run_direct_stage(
                "Conservative Analyst",
                AGENT_SPECS[stage_key]["stage_slug"],
                nodes[stage_key],
                state,
                "risk_debate_state",
                tracer,
                run_root,
            )
        elif stage_key == "neutral_risk_analyst":
            run_direct_stage(
                "Neutral Analyst",
                AGENT_SPECS[stage_key]["stage_slug"],
                nodes[stage_key],
                state,
                "risk_debate_state",
                tracer,
                run_root,
            )
        elif stage_key == "portfolio_manager":
            run_direct_stage(
                "Portfolio Manager",
                AGENT_SPECS[stage_key]["stage_slug"],
                nodes[stage_key],
                state,
                "final_trade_decision",
                tracer,
                run_root,
            )
    answer = _run_followup(
        agent_key=agent_key,
        graph=graph,
        tracer=tracer,
        state=state,
        ticker=ticker.upper(),
        trade_date=trade_date,
        user_request=user_request,
        output_dir=run_root,
    )

    json_dump(
        run_root / "session_summary.json",
        {
            "ticker": ticker.upper(),
            "trade_date": trade_date,
            "agent_key": agent_key,
            "display_name": AGENT_SPECS[agent_key]["display_name"],
            "user_request": user_request,
            "required_data": AGENT_SPECS[agent_key]["required_data"],
            "execution_plan": plan,
            "output_dir": str(run_root),
        },
    )
    write_markdown(run_root / "selected_answer.md", answer)

    return {
        "ticker": ticker.upper(),
        "trade_date": trade_date,
        "agent_key": agent_key,
        "display_name": AGENT_SPECS[agent_key]["display_name"],
        "required_data": AGENT_SPECS[agent_key]["required_data"],
        "execution_plan": plan,
        "user_request": user_request,
        "answer": answer,
        "output_dir": str(run_root),
    }
