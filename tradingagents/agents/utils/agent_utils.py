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

def build_etf_risk_block(ticker: str) -> str:
    """Risk-debate-specific ETF axes, returned as a markdown block.

    The three risk debators (aggressive / conservative / neutral) consume
    the analyst reports but otherwise have no ETF awareness — without this
    block they argue about "company financials" of a fund. Each axis below
    matters to a different debator:

    - liquidity / structure → conservative emphasis
    - leverage / sector momentum → aggressive emphasis
    - concentration / diversification fit → neutral emphasis

    Returns an empty string for non-ETF tickers so debators can append
    unconditionally without branching.
    """
    if not is_etf_ticker(ticker):
        return ""
    return (
        "\n\n**ETF-specific risk dimensions** (this instrument is an exchange-traded "
        "fund, not a company — weigh these axes alongside the analyst reports):\n"
        "- **Liquidity**: AUM size and daily turnover; small-AUM ETFs slip on "
        "moderate sizes and can trade at persistent discounts to NAV.\n"
        "- **Concentration**: top-10 aggregate weight and Herfindahl index "
        "(see the holdings report). High concentration means the ETF inherits "
        "single-name risk from a few large positions.\n"
        "- **Tracking risk**: expense-ratio drag and tracking error vs the stated "
        "benchmark erode long-horizon returns.\n"
        "- **Structure risk**: leveraged or inverse ETFs decay daily — long-term "
        "framing is inappropriate. Synthetic / swap-based ETFs add counterparty risk.\n"
        "- **Premium/discount to NAV**: persistent divergence signals "
        "authorized-participant or arbitrage friction.\n"
        "- **Underlying-name catalysts**: see the drill-down section in the "
        "fundamentals report (if present) for top-constituent news and fundamentals."
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


        
