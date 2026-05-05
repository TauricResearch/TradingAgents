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


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )


def get_evidence_discipline_instruction(role: str) -> str:
    """Shared prompt guardrails that keep recommendations evidence-bound.

    This is intentionally text-only so it can be appended to both chat-tool
    analyst prompts and direct debate prompts without changing their call
    interfaces.
    """
    return f"""

Evidence discipline for the {role}:
- Be objective: Do not force a conservative conclusion, and do not force a bullish conclusion. Evidence strength, not tone or role bias, determines the recommendation.
- Separate Facts, Inferences, and Assumptions. A claim based on a competitor, sector theme, or social-media guess is an inference unless the data directly names the instrument.
- Include an **Evidence Check** table with these columns when producing a report or decision: Claim | Supporting Data | Source/Report | Confidence | Missing Evidence.
- Include **Unsupported Assumptions** for important claims that lack direct data. Do not use unsupported assumptions as the sole basis for Buy, Sell, Overweight, or Underweight.
- For fundamentals, distinguish headline net profit from recurring/core profit when data allows; call out investment income, fair-value changes, cash flow quality, inventory growth, and one-off items separately.
- For news and sentiment, lower confidence when there is no direct company news or no real social-media sample. Do not present inferred market mood as measured sentiment.
- For technical analysis, connect entries and stops to explicit price levels and calculate whether the risk/reward is attractive.
- End with **Decision Impact**: explain how the evidence changes the action, what would upgrade the view, and what would downgrade the view.
"""


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


        
