"""Holding Reviewer LLM agent.

Reviews all open positions in a portfolio and recommends HOLD or SELL for each,
based on current P&L, price momentum, and news sentiment.

Pattern: ``create_holding_reviewer(llm)`` → closure (scanner agent pattern).
Uses ``run_tool_loop()`` for inline tool execution.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.json_utils import extract_json
from tradingagents.agents.utils.news_data_tools import get_news
from tradingagents.agents.utils.tool_runner import run_tool_loop

logger = logging.getLogger(__name__)


def _analysis_has_deep_dive(analysis: Any) -> bool:
    """Return True when a ticker analysis contains a completed deep-dive decision."""
    if not isinstance(analysis, dict):
        return False
    status = str(analysis.get("analysis_status") or "").strip().lower()
    if status == "aborted":
        return False
    if status == "completed":
        return True
    return bool(str(analysis.get("final_trade_decision") or "").strip())


def _extract_rating(decision_text: str) -> str:
    """Extract a saved PM-style rating label from final_trade_decision text."""
    if not decision_text:
        return ""
    match = re.search(r"rating\s*:\s*([A-Za-z -]+)", decision_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _analysis_snapshot(analysis: dict) -> dict[str, str]:
    """Build a compact prior-thesis snapshot for holding review."""
    if not _analysis_has_deep_dive(analysis):
        return {}
    final_decision = str(analysis.get("final_trade_decision") or "").strip()
    return {
        "rating": _extract_rating(final_decision),
        "final_trade_decision": final_decision[:600],
        "trader_plan": str(analysis.get("trader_investment_plan") or "").strip()[:320],
        "research_plan": str(analysis.get("investment_plan") or "").strip()[:320],
        "market_report": str(analysis.get("market_report") or "").strip()[:240],
        "fundamentals_report": str(analysis.get("fundamentals_report") or "").strip()[:240],
    }


def create_holding_reviewer(llm):
    """Create a holding reviewer agent node.

    Args:
        llm: A LangChain chat model instance.

    Returns:
        A node function ``holding_reviewer_node(state)`` compatible with LangGraph.
    """

    def holding_reviewer_node(state):
        portfolio_data_str = state.get("portfolio_data") or "{}"
        analysis_date = state.get("analysis_date") or ""

        try:
            portfolio_data = json.loads(portfolio_data_str)
        except (json.JSONDecodeError, TypeError):
            portfolio_data = {}

        holdings = portfolio_data.get("holdings") or []
        portfolio_name = portfolio_data.get("portfolio", {}).get("name", "Portfolio")
        ticker_analyses = state.get("ticker_analyses") or {}

        if not holdings:
            return {
                "holding_reviews": json.dumps({}),
                "sender": "holding_reviewer",
            }

        holdings_summary = "\n".join(
            f"- {h.get('ticker', '?')}: {h.get('shares', 0):.2f} shares @ avg cost "
            f"${h.get('avg_cost', 0):.2f} | sector: {h.get('sector', 'Unknown')}"
            for h in holdings
        )
        holding_tickers = [
            str(h.get("ticker") or "").upper()
            for h in holdings
            if isinstance(h, dict) and str(h.get("ticker") or "").strip()
        ]
        deep_dive_context: dict[str, dict[str, str]] = {}
        if isinstance(ticker_analyses, dict):
            for ticker in holding_tickers:
                snapshot = _analysis_snapshot(ticker_analyses.get(ticker, {}))
                if snapshot:
                    deep_dive_context[ticker] = snapshot
        deep_dive_str = (
            json.dumps(deep_dive_context, indent=2)
            if deep_dive_context
            else "No completed deep-dive ticker analyses available for current holdings."
        )

        tools = [get_stock_data, get_news]

        system_message = (
            f"You are a portfolio analyst reviewing all open positions in '{portfolio_name}'. "
            f"The analysis date is {analysis_date}. "
            f"You hold the following positions:\n{holdings_summary}\n\n"
            "## Completed Deep Dive Analyses (authoritative prior thesis context)\n"
            f"{deep_dive_str}\n\n"
            "For each holding, use the completed deep-dive analysis as the primary source for the "
            "original thesis and risk framing whenever that analysis is available. Use get_stock_data "
            "to retrieve recent price history and get_news to check recent sentiment. "
            "Treat those tools as an update layer on top of the saved deep-dive thesis, not as a "
            "replacement for it. If updated price/news evidence contradicts the prior thesis, explain "
            "exactly why the thesis is broken and recommend SELL. If the thesis remains intact, prefer HOLD. "
            "If a holding has no completed deep-dive analysis, say that prior thesis context is missing and "
            "review conservatively from the available market/news evidence. "
            "Then produce a JSON object where each key is a ticker symbol and the value is:\n"
            "{\n"
            '  "ticker": "...",\n'
            '  "recommendation": "HOLD" or "SELL",\n'
            '  "confidence": "high" or "medium" or "low",\n'
            '  "rationale": "...",\n'
            '  "key_risks": ["..."]\n'
            "}\n\n"
            "Consider: current unrealized P&L, price momentum, news sentiment, "
            "the completed deep-dive thesis, and whether that thesis still holds. "
            "Output ONLY valid JSON with ticker → review mapping. "
            "Start your final response with '{' and end with '}'. "
            "Do NOT use markdown code fences."
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([t.name for t in tools]))
        prompt = prompt.partial(current_date=analysis_date)

        chain = prompt | llm.bind_tools(tools)
        result = run_tool_loop(chain, [], tools)

        raw = result.content or "{}"
        try:
            parsed = extract_json(raw)
            reviews_str = json.dumps(parsed)
        except (ValueError, json.JSONDecodeError):
            logger.warning(
                "holding_reviewer: could not extract JSON; storing raw (first 200): %s",
                raw[:200],
            )
            reviews_str = raw

        return {
            "messages": [result],
            "holding_reviews": reviews_str,
            "sender": "holding_reviewer",
        }

    return holding_reviewer_node
