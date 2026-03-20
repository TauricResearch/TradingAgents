"""Holding Reviewer LLM agent.

Reviews all open positions in a portfolio and recommends HOLD or SELL for each,
based on current P&L, price momentum, and news sentiment.

Pattern: ``create_holding_reviewer(llm)`` → closure (scanner agent pattern).
Uses ``run_tool_loop()`` for inline tool execution.
"""

from __future__ import annotations

import json
import logging

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.json_utils import extract_json
from tradingagents.agents.utils.news_data_tools import get_news
from tradingagents.agents.utils.tool_runner import run_tool_loop

logger = logging.getLogger(__name__)


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

        tools = [get_stock_data, get_news]

        system_message = (
            f"You are a portfolio analyst reviewing all open positions in '{portfolio_name}'. "
            f"The analysis date is {analysis_date}. "
            f"You hold the following positions:\n{holdings_summary}\n\n"
            "For each holding, use get_stock_data to retrieve recent price history "
            "and get_news to check recent sentiment. "
            "Then produce a JSON object where each key is a ticker symbol and the value is:\n"
            "{\n"
            '  "ticker": "...",\n'
            '  "recommendation": "HOLD" or "SELL",\n'
            '  "confidence": "high" or "medium" or "low",\n'
            '  "rationale": "...",\n'
            '  "key_risks": ["..."]\n'
            "}\n\n"
            "Consider: current unrealized P&L, price momentum, news sentiment, "
            "and whether the original thesis still holds. "
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
        result = run_tool_loop(chain, state["messages"], tools)

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
