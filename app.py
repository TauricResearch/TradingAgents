"""Chainlit web UI for TradingAgents — deployed on Railway."""

import os
import re
from datetime import date

import chainlit as cl

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from cli.stats_handler import StatsCallbackHandler


def parse_ticker_date(text: str):
    """Extract ticker symbol and optional date from user message.

    Examples:
        "NVDA"                       -> ("NVDA", today)
        "Analyze AAPL 2024-12-01"    -> ("AAPL", "2024-12-01")
        "What about TSLA?"           -> ("TSLA", today)
    """
    # Try to find a date (YYYY-MM-DD)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    trade_date = date_match.group(1) if date_match else str(date.today())

    # Find uppercase 1-5 letter words as candidate tickers
    candidates = re.findall(r"\b([A-Z]{1,5})\b", text)
    # Filter out common English words
    skip = {"I", "A", "THE", "AND", "OR", "FOR", "TO", "IN", "ON", "AT", "IS",
            "IT", "OF", "BY", "AS", "AN", "BE", "IF", "SO", "DO", "MY", "UP",
            "NO", "NOT", "ALL", "BUT", "HOW", "GET", "HAS", "HAD", "CAN",
            "WHAT", "ABOUT", "BUY", "SELL", "HOLD"}
    tickers = [c for c in candidates if c not in skip]

    ticker = tickers[0] if tickers else None
    return ticker, trade_date


def build_config():
    """Build TradingAgents config for Anthropic/Claude."""
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "anthropic"
    config["deep_think_llm"] = os.getenv("DEEP_THINK_MODEL", "claude-sonnet-4-5-20241022")
    config["quick_think_llm"] = os.getenv("QUICK_THINK_MODEL", "claude-haiku-4-5-20251001")
    config["backend_url"] = None
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    config["data_vendors"] = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    }
    return config


# Report field -> display name
REPORT_NAMES = {
    "market_report": "Market Analyst",
    "sentiment_report": "Sentiment Analyst",
    "news_report": "News Analyst",
    "fundamentals_report": "Fundamentals Analyst",
}


@cl.on_chat_start
async def on_chat_start():
    await cl.Message(
        content=(
            "**TradingAgents** — Multi-Agent LLM Trading Analysis\n\n"
            "Send a ticker symbol to analyze. Examples:\n"
            "- `NVDA`\n"
            "- `Analyze AAPL 2024-12-01`\n"
            "- `What's the outlook for TSLA?`\n\n"
            "I'll run a team of AI analysts, researchers, traders, and risk managers "
            "to produce a trading decision."
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    ticker, trade_date = parse_ticker_date(message.content)

    if not ticker:
        await cl.Message(
            content="I couldn't find a ticker symbol. Try something like `NVDA` or `Analyze AAPL 2024-12-01`."
        ).send()
        return

    # Status message
    status_msg = cl.Message(content=f"Analyzing **{ticker}** for **{trade_date}**...")
    await status_msg.send()

    # Build graph
    config = build_config()
    stats = StatsCallbackHandler()

    try:
        graph = TradingAgentsGraph(
            selected_analysts=["market", "social", "news", "fundamentals"],
            debug=False,
            config=config,
            callbacks=[stats],
        )
    except Exception as e:
        await cl.Message(content=f"Failed to initialize agents: {e}").send()
        return

    # Create initial state and stream
    init_state = graph.propagator.create_initial_state(ticker, trade_date)
    args = graph.propagator.get_graph_args(callbacks=[stats])

    # Track which reports/phases we've already shown
    seen_reports = set()
    seen_debate = False
    seen_risk = False
    seen_trader = False
    final_state = None

    try:
        async for chunk in graph.graph.astream(init_state, **args):
            final_state = chunk

            # --- Analyst reports ---
            for field, name in REPORT_NAMES.items():
                if field not in seen_reports and chunk.get(field):
                    seen_reports.add(field)
                    report = chunk[field]
                    # Show as a collapsible Step
                    async with cl.Step(name=f"{name} Report", type="tool") as step:
                        step.output = report[:3000] if len(report) > 3000 else report

            # --- Investment debate (Bull vs Bear) ---
            debate = chunk.get("investment_debate_state")
            if debate and not seen_debate and debate.get("judge_decision"):
                seen_debate = True
                async with cl.Step(name="Research Debate", type="tool") as step:
                    step.output = (
                        f"**Judge Decision:**\n{debate['judge_decision']}"
                    )

            # --- Trader plan ---
            if not seen_trader and chunk.get("trader_investment_plan"):
                seen_trader = True
                async with cl.Step(name="Trader Plan", type="tool") as step:
                    step.output = chunk["trader_investment_plan"][:3000]

            # --- Risk debate ---
            risk = chunk.get("risk_debate_state")
            if risk and not seen_risk and risk.get("judge_decision"):
                seen_risk = True
                async with cl.Step(name="Risk Assessment", type="tool") as step:
                    step.output = f"**Risk Decision:**\n{risk['judge_decision']}"

    except Exception as e:
        await cl.Message(content=f"Error during analysis: {e}").send()
        return

    if not final_state:
        await cl.Message(content="Analysis produced no results.").send()
        return

    # Process final decision
    decision_text = final_state.get("final_trade_decision", "No decision reached.")
    signal = graph.process_signal(decision_text)

    # Stats summary
    s = stats.get_stats()
    stats_line = (
        f"*{s['llm_calls']} LLM calls · {s['tool_calls']} tool calls · "
        f"{s['tokens_in']:,} tokens in · {s['tokens_out']:,} tokens out*"
    )

    await cl.Message(
        content=(
            f"## {ticker} — Trading Decision\n\n"
            f"**Signal: {signal}**\n\n"
            f"---\n\n"
            f"{decision_text}\n\n"
            f"---\n{stats_line}"
        )
    ).send()
