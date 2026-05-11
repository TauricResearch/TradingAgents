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
from tradingagents.agents.utils.etf_tools import (
    get_etf_profile,
    get_etf_holdings,
    get_etf_top_holdings_drilldown,
)
# Re-export so analyst modules don't have to reach into dataflows for the
# detection helper — keeps the agent-layer import surface in one place.
from tradingagents.dataflows.etf_utils import is_etf_ticker  # noqa: F401


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Applied to every agent whose output reaches the saved report —
    analysts, researchers, debaters, research manager, trader, and
    portfolio manager — so a non-English run produces a fully localized
    report rather than a mix of languages.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers.

    For ETF tickers the prompt is augmented with ETF-specific analysis
    guidance — top-holding concentration, tracking strategy, expense ratio,
    NAV / premium-discount — and a redirect away from the company-financial
    tools (which now return ETF-not-applicable placeholders).
    """
    base = (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )

    if is_etf_ticker(ticker):
        base += (
            "\n\n**This instrument is an ETF (exchange-traded fund), not a company.**"
            "\n- Analyze it by top-holding concentration, tracking index / underlying basket, "
            "expense ratio, AUM trend, premium/discount to NAV, and the underlying sector "
            "or index momentum."
            "\n- Do NOT analyze it as a company — it has no income statement, balance sheet, "
            "or cash flow of its own. The company-financial tools (`get_fundamentals`, "
            "`get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_insider_transactions`) "
            "will return ETF-not-applicable placeholders for this ticker."
            "\n- Use `get_etf_profile` and `get_etf_holdings` for ETF-relevant data."
        )
    return base

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


        
