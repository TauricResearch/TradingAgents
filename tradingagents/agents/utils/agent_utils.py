from langchain_core.messages import HumanMessage, RemoveMessage

# Re-export all tool functions so analysts can import from agent_utils directly.
# These imports are intentional public re-exports, NOT unused imports.
from tradingagents.agents.utils.core_stock_tools import get_stock_data as get_stock_data
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators as get_indicators,
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals as get_fundamentals,
    get_balance_sheet as get_balance_sheet,
    get_cashflow as get_cashflow,
    get_income_statement as get_income_statement,
)
from tradingagents.agents.utils.news_data_tools import (
    get_news as get_news,
    get_global_news as get_global_news,
    get_insider_transactions as get_insider_transactions,
    get_social_sentiment as get_social_sentiment,
)

__all__ = [
    "create_msg_delete",
    "get_stock_data",
    "get_indicators",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_news",
    "get_global_news",
    "get_insider_transactions",
    "get_social_sentiment",
]

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

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages
