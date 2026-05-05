import json

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
from tradingagents.agents.utils.trade_levels_tools import (
    suggest_trade_levels
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        tool_errors = state.get("tool_errors", [])
        error_count = int(state.get("error_count", 0) or 0)
        tool_call_count = int(state.get("tool_call_count", 0) or 0)
        trade_levels = state.get("trade_levels")

        for m in messages:
            mtype = getattr(m, "type", None)
            if mtype != "tool":
                continue
            tool_call_count += 1
            content = getattr(m, "content", None)
            if not isinstance(content, str):
                continue
            try:
                payload = json.loads(content)
            except Exception:
                continue
            if isinstance(payload, dict) and payload.get("error") is True:
                error_count += 1
                tool_errors.append(payload)
            if (
                isinstance(payload, dict)
                and payload.get("error") is not True
                and "entry_condition" in payload
                and "entry_price" in payload
                and "stop_loss" in payload
                and "anchors" in payload
            ):
                trade_levels = payload

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {
            "messages": removal_operations + [placeholder],
            "tool_errors": tool_errors,
            "error_count": error_count,
            "tool_call_count": tool_call_count,
            "trade_levels": trade_levels,
        }

    return delete_messages


        
