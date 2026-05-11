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


def get_horizon_instruction() -> str:
    """Return a prompt instruction for the configured investment horizon.
    
    Returns guidance string based on investment horizon in config.
    """
    from tradingagents.dataflows.config import get_config
    
    horizon = get_config().get("investment_horizon", "medium_term")
    
    horizon_guidance = {
        "1_day": "Focus on: intraday volatility, momentum indicators (MACD, RSI), bid-ask spreads, and execution timing. Prioritize short-term signals only.",
        "1_week": "Focus on: weekly momentum, support/resistance levels, and event-driven price moves. Balance technical signals with short-term catalysts.",
        "1_month": "Focus on: monthly trends, technical breakouts, and news-driven catalysts. Give equal weight to technicals and short-term fundamentals.",
        "6_months": "Balance: technical trends (60%) and fundamental signals (40%). Look for medium-term momentum and valuation support.",
        "1_year": "Balance: fundamental value (70%) and technical confirmation (30%). Focus on earnings trends, valuation multiples, and macro factors.",
        "5_years_plus": "Focus on: structural demand drivers, supply constraints, industry trends, and long-term valuation multiples. Ignore short-term technical noise like MACD crossovers or 50-day SMA.",
        "medium_term": "Balance technical and fundamental analysis equally for medium-term trading decisions.",
    }
    
    guidance = horizon_guidance.get(horizon, horizon_guidance["medium_term"])
    return f" Investment Horizon: {horizon}. Analysis Priority: {guidance} Adapt your analysis based on this investment horizon."


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


        
