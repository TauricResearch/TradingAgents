from langchain_core.messages import HumanMessage, RemoveMessage

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


def get_language_instruction() -> str:
    """
    Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Applied to every agent whose output reaches the saved report — analysts,
    researchers, debaters, research manager, trader, and portfolio manager —
    so a non-English run produces a fully localized report rather than a mix
    of languages.
    """
    from tradingagents.dataflows.config import get_config

    lang = get_config().get("output_language", "English")

    if lang.strip().lower() == "english":
        return ""

    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str, asset_type: str = "stock") -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    instrument_label = "asset" if asset_type == "crypto" else "instrument"

    extra_hint = (
        " Treat it as a crypto asset rather than a company, and do not assume company fundamentals are available."
        if asset_type == "crypto"
        else ""
    )

    return (
        f"The {instrument_label} to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`)."
        + extra_hint
    )


def _build_workflow_placeholder(state) -> HumanMessage:
    ticker = state.get("company_of_interest", "the requested instrument")
    trade_date = state.get("trade_date", "the requested date")
    asset_type = state.get("asset_type", "stock")

    return HumanMessage(
        content=(
            "Proceed with your assigned analysis for this TradingAgents workflow. "
            f"The instrument to analyze is `{ticker}`. "
            "Use this exact ticker in every tool call, report, and recommendation. "
            f"The asset type is {asset_type}. "
            f"The analysis date is {trade_date}. "
            "Do not treat this placeholder as a standalone user request."
        )
    )


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add a context-aware placeholder for compatibility."""
        messages = state["messages"]

        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        placeholder = _build_workflow_placeholder(state)

        return {"messages": removal_operations + [placeholder]}

    return delete_messages