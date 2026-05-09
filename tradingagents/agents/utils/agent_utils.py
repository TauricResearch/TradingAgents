from langchain_core.messages import HumanMessage, RemoveMessage

# Re-export tool functions so agent modules can import from a single location.
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.fundamental_data_tools import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
)
from tradingagents.agents.utils.news_data_tools import (
    get_global_news,
    get_insider_transactions,
    get_news,
)
from tradingagents.agents.utils.technical_indicators_tools import get_indicators

__all__ = [
    "get_stock_data",
    "get_indicators",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_news",
    "get_insider_transactions",
    "get_global_news",
    "get_language_instruction",
    "build_instrument_context",
    "create_msg_delete",
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
    """Describe the exact instrument so agents preserve exchange-qualified tickers
    and use the correct company identity instead of guessing from the symbol."""
    from tradingagents.dataflows.y_finance import get_instrument_metadata

    base = (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )

    metadata = get_instrument_metadata(ticker)
    if not metadata:
        return base

    parts = []
    name = metadata.get("name")
    exchange = metadata.get("exchange")
    currency = metadata.get("currency")
    if name:
        parts.append(f"company name `{name}`")
    if exchange:
        parts.append(f"listed on `{exchange}`")
    if currency:
        parts.append(f"quoted in `{currency}`")
    if not parts:
        return base

    return (
        f"{base} This ticker refers to {', '.join(parts)}. "
        "Use this exact company identity in your report — do not substitute a "
        "similarly-named instrument from a different exchange."
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
