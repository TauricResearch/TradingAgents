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
    get_global_news,
    get_company_announcements,
    get_company_event_signals,
    get_market_activity,
    get_sector_rotation_context,
    get_sector_strength_snapshot,
    get_relative_strength_context,
    get_trading_constraint_context,
    get_limit_move_sentiment_context,
    get_peer_comparison_context,
    get_corporate_action_pressure_context,
    get_unusual_trading_activity,
    get_capital_flow_regime_context,
    get_decision_signal_summary,
    get_xueqiu_sentiment,
    get_caixin_news,
)


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


def is_a_share_ticker(ticker: str) -> bool:
    """Return True when ``ticker`` looks like an exchange-qualified A-share."""
    ticker_upper = ticker.strip().upper()
    return ticker_upper.endswith((".SH", ".SZ", ".BJ"))


def build_market_rule_context(ticker: str, asset_type: str = "stock") -> str:
    """Inject market-structure constraints that materially affect decisions."""
    if asset_type != "stock" or not is_a_share_ticker(ticker):
        return ""

    return (
        "A-share market constraints and context: "
        "China A-shares are effectively T+1 for selling after a buy, have daily price limits for most names "
        "(commonly 10%, 20% on ChiNext/STAR after registration-based reform, and different limits for ST/*ST names), "
        "may be suspended, and often react strongly to policy, exchange announcements, lock-up expiries, shareholder "
        "reductions/increases, and sector rotation. Do not assume easy intraday exit, unrestricted shorting, or US-style "
        "liquidity. Treat official announcements, trading halts, risk-warning labels, and price-limit behavior as first-class risks."
    )


def build_a_share_research_focus(ticker: str, asset_type: str = "stock") -> str:
    """Return a concise checklist of A-share-specific research priorities."""
    if asset_type != "stock" or not is_a_share_ticker(ticker):
        return ""

    return (
        "When reasoning about this A-share, pay special attention to: policy direction, sector/theme rotation, "
        "earnings pre-announcements, official company announcements, trading suspensions, ST risk, lock-up expiry, "
        "shareholder reductions/increases, and whether recent moves could be explained by short-term sentiment rather than fundamentals."
    )


def build_instrument_context(ticker: str, asset_type: str = "stock") -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    instrument_label = "asset" if asset_type == "crypto" else "instrument"
    extra_hint = (
        " Treat it as a crypto asset rather than a company, and do not assume company fundamentals are available."
        if asset_type == "crypto"
        else ""
    )
    ticker_examples = "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`)."
    if asset_type == "stock" and ticker[:1].isdigit():
        ticker_examples = (
            "preserving any exchange suffix (e.g. `600519.SH`, `000001.SZ`, `430047.BJ`)."
        )
    return (
        f"The {instrument_label} to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        + ticker_examples
        + extra_hint
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


        
