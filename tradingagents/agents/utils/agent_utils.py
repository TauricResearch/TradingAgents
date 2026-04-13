from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.instruments import get_asset_class
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
    """Describe the instrument format so agents preserve the exact symbol."""
    asset_class = get_asset_class(ticker)
    if asset_class == "crypto":
        return (
            f"The instrument to analyze is `{ticker}` (cryptocurrency). "
            "Use this exact symbol in every tool call, report, and recommendation, "
            "preserving the base/quote pair format (e.g. `BTC-USD`, `ETH-USD`). "
            "Crypto markets trade 24/7, so do not assume weekends are closed."
        )

    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )


def build_fundamentals_context(ticker: str) -> str:
    """Return asset-aware guidance for the fundamentals analyst."""
    if get_asset_class(ticker) == "crypto":
        return (
            "For cryptocurrency instruments, interpret fundamentals as tokenomics and market structure: "
            "supply dynamics, liquidity, exchange coverage, adoption indicators, and macro/regulatory drivers. "
            "If company financial statements or insider filings are unavailable, explicitly mark those sections as N/A."
        )
    return (
        "For equities, prioritize corporate fundamentals such as business profile, profitability, "
        "cash flow quality, leverage, and financial statement trends."
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


        
