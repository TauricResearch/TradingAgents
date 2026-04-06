from langchain_core.messages import HumanMessage, RemoveMessage
import re

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
    lang = get_output_language()
    if lang.strip().lower() == "english":
        return ""
    return (
        f" Write your entire response in {lang}. "
        f"Do not mix in English for headings, summaries, recommendations, table labels, or narrative text. "
        f"Keep only ticker symbols, company names, dates, and raw numeric values unchanged when needed."
    )


def get_output_language() -> str:
    from tradingagents.dataflows.config import get_config

    return str(get_config().get("output_language", "English")).strip() or "English"


def rewrite_in_output_language(llm, content: str, *, content_type: str = "report") -> str:
    """Rewrite already-generated content into the configured output language.

    This lets the graph keep English-centric reasoning prompts where useful while
    ensuring the persisted user-facing report is consistently localized.
    """
    if not content:
        return content

    lang = get_output_language()
    if lang.lower() == "english":
        return content

    messages = [
        (
            "system",
            "You are a financial editor rewriting existing analysis for end users. "
            f"Rewrite the user's {content_type} entirely in {lang}. "
            "Requirements: preserve the original meaning, preserve markdown structure, preserve tables, preserve ticker symbols, preserve dates, preserve numbers, and preserve factual details. "
            "Translate all headings, labels, bullet text, narrative prose, recommendations, quoted headlines, and English source titles so the output reads naturally and consistently in the target language. "
            "Do not leave English article titles or English section names in the output unless they are unavoidable proper nouns or acronyms. "
            "Keep only unavoidable Latin-script proper nouns or acronyms such as ticker symbols, company names, product names, RSI, MACD, ATR, EBITDA, and CAPEX. "
            "If the source contains English control phrases or analyst role labels, rewrite them into natural user-facing target-language labels. "
            "Output only the rewritten content.",
        ),
        ("human", content),
    ]

    rewritten = llm.invoke(messages).content
    if not isinstance(rewritten, str) or not rewritten.strip():
        return content
    return _normalize_localized_finance_terms(rewritten, lang)


def _normalize_localized_finance_terms(content: str, language: str) -> str:
    if language.strip().lower() != "korean":
        return content

    replacements = {
        "FINAL TRANSACTION PROPOSAL": "최종 거래 제안",
        "**BUY**": "**매수**",
        "**HOLD**": "**보유**",
        "**SELL**": "**매도**",
        "**OVERWEIGHT**": "**비중 확대**",
        "**UNDERWEIGHT**": "**비중 축소**",
    }

    normalized = content
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    regex_replacements = (
        (r"\bBuy\b", "매수"),
        (r"\bHold\b", "보유"),
        (r"\bSell\b", "매도"),
        (r"\bOverweight\b", "비중 확대"),
        (r"\bUnderweight\b", "비중 축소"),
        (r"\bBUY\b", "매수"),
        (r"\bHOLD\b", "보유"),
        (r"\bSELL\b", "매도"),
        (r"\bOVERWEIGHT\b", "비중 확대"),
        (r"\bUNDERWEIGHT\b", "비중 축소"),
    )
    for pattern, replacement in regex_replacements:
        normalized = re.sub(pattern, replacement, normalized)
    return normalized


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


        
