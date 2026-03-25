from collections.abc import Mapping
import json
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
from tradingagents.agents.utils.scenario_tools import (
    get_catalyst_calendar,
    get_scenario_fundamentals,
    get_scenario_news,
)
from tradingagents.agents.utils.segment_tools import (
    get_segment_fundamentals,
    get_segment_income_statement,
    get_segment_news,
)
from tradingagents.agents.utils.sizing_tools import (
    get_sizing_fundamentals,
    get_sizing_indicator,
    get_sizing_price_history,
)
from tradingagents.agents.utils.valuation_tools import (
    get_valuation_inputs,
)


__all__ = [
    "build_instrument_context",
    "build_analyst_report_context",
    "build_structured_stock_context",
    "build_structured_stock_priority_context",
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
    "get_catalyst_calendar",
    "get_scenario_fundamentals",
    "get_scenario_news",
    "get_segment_fundamentals",
    "get_segment_income_statement",
    "get_segment_news",
    "get_sizing_fundamentals",
    "get_sizing_indicator",
    "get_sizing_price_history",
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


def build_structured_stock_context(state: Mapping[str, Any]) -> str:
    """Render structured underwriting outputs into prompt-friendly text."""
    sections = []

    segment_data = state.get("segment_data", {})
    if segment_data:
        sections.append(
            "Structured segment analysis:\n"
            + json.dumps(segment_data, indent=2, sort_keys=True)
        )

    scenario_catalyst_data = state.get("scenario_catalyst_data", {})
    if scenario_catalyst_data:
        sections.append(
            "Structured scenario and catalyst analysis:\n"
            + json.dumps(scenario_catalyst_data, indent=2, sort_keys=True)
        )

    position_sizing_data = state.get("position_sizing_data", {})
    if position_sizing_data:
        sections.append(
            "Structured position sizing analysis:\n"
            + json.dumps(position_sizing_data, indent=2, sort_keys=True)
        )

    return "\n\n".join(section for section in sections if section)


def build_structured_stock_priority_context(state: Mapping[str, Any]) -> str:
    structured_context = build_structured_stock_context(state)
    if not structured_context:
        return ""
    return (
        "Prioritize the structured stock underwriting outputs below as primary evidence. "
        "Anchor your reasoning first on numeric fields such as revenue_share_pct, "
        "probability_pct, target_weight_pct, initial_weight_pct, and max_loss_pct "
        "before using freeform analyst reports for narrative color.\n\n"
        + structured_context
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
