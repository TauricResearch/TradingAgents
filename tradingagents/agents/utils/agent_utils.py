from collections.abc import Mapping
from typing import Any

from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)
from tradingagents.agents.utils.macro_data_tools import (
    get_economic_indicators,
    get_fed_calendar,
    get_yield_curve,
)
from tradingagents.agents.utils.valuation_tools import (
    get_valuation_inputs,
)


__all__ = [
    "build_instrument_context",
    "build_analyst_report_context",
    "create_msg_delete",
    "get_balance_sheet",
    "get_cashflow",
    "get_economic_indicators",
    "get_fed_calendar",
    "get_fundamentals",
    "get_global_news",
    "get_income_statement",
    "get_indicators",
    "get_insider_transactions",
    "get_news",
    "get_stock_data",
    "get_valuation_inputs",
    "get_yield_curve",
]


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )


def build_analyst_report_context(state: Mapping[str, Any]) -> str:
    """Build a stable analyst context block for downstream prompts and memory."""
    sections = [
        ("Market Research Report", state.get("market_report", "")),
        ("Social Media Sentiment Report", state.get("sentiment_report", "")),
        ("Latest World Affairs Report", state.get("news_report", "")),
        ("Macro Economic Report", state.get("macro_report", "")),
        ("Company Fundamentals Report", state.get("fundamentals_report", "")),
        ("Factor Rules Report", state.get("factor_rules_report", "")),
    ]
    return "\n".join(
        f"{label}: {content}" for label, content in sections if content
    )


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages
