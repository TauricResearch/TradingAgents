import logging
import functools
from typing import Any, Mapping

import yfinance as yf
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

logger = logging.getLogger(__name__)


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


def _clean_identity_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"none", "n/a", "nan", "null"}:
        return None
    return cleaned


@functools.lru_cache(maxsize=128)
def resolve_instrument_identity(ticker: str) -> dict[str, str]:
    """Resolve deterministic company identity metadata for a ticker.

    This is intentionally best-effort: if yfinance is unavailable, rate-limited,
    or does not know the ticker, the graph should still run with ticker-only
    context rather than fail before analysis starts.
    """
    try:
        info = yf.Ticker(ticker.upper()).info or {}
    except Exception as exc:
        logger.debug("Could not resolve instrument identity for %s: %s", ticker, exc)
        return {}

    identity: dict[str, str] = {}
    company_name = _clean_identity_value(info.get("longName")) or _clean_identity_value(
        info.get("shortName")
    )
    if company_name:
        identity["company_name"] = company_name

    for source_key, target_key in (
        ("sector", "sector"),
        ("industry", "industry"),
        ("exchange", "exchange"),
        ("quoteType", "quote_type"),
    ):
        value = _clean_identity_value(info.get(source_key))
        if value:
            identity[target_key] = value

    return identity


def build_instrument_context(
    ticker: str,
    identity: Mapping[str, str] | None = None,
) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    context = (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )

    if not identity:
        return context

    details = []
    company_name = identity.get("company_name") or identity.get("name")
    if company_name:
        details.append(f"Company: {company_name}")

    sector = identity.get("sector")
    industry = identity.get("industry")
    if sector and industry:
        details.append(f"Business classification: {sector} / {industry}")
    elif sector:
        details.append(f"Sector: {sector}")
    elif industry:
        details.append(f"Industry: {industry}")

    exchange = identity.get("exchange")
    if exchange:
        details.append(f"Exchange: {exchange}")

    quote_type = identity.get("quote_type")
    if quote_type:
        details.append(f"Quote type: {quote_type}")

    if not details:
        return context

    return (
        f"{context} Resolved instrument identity: {'; '.join(details)}. "
        "Do not substitute a different company or ticker unless a tool result "
        "explicitly disproves this resolved identity."
    )


def get_instrument_context_from_state(state: Mapping[str, Any]) -> str:
    context = state.get("instrument_context")
    if isinstance(context, str) and context.strip():
        return context
    return build_instrument_context(str(state["company_of_interest"]))


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


        
