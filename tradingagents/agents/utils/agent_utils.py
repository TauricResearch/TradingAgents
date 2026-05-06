"""Shared helper utilities and placeholder tool stubs for agent factories.

The crypto/Kalshi tool implementations land in Phase 1 (under
``tradingagents/dataflows/``). Phase 2 rewires the analyst factories
to import their tools directly from the dataflows package and the
placeholders below go away. They exist now only so the analyst
modules and the graph wiring continue to import cleanly during
Phases 0–1.
"""

from typing import Annotated

from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.tools import tool


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


def build_instrument_context(contract_id: str) -> str:
    """Describe the exact Kalshi contract under analysis so agents preserve the identifier.

    The framework analyzes Kalshi binary prediction-market contracts (not
    equities); ``contract_id`` is the Kalshi-issued ticker such as
    ``KXBTCD-26MAY05-T100000`` for a daily BTC contract. Phase 2 enriches
    this context with the underlying asset and resolution rules.
    """
    return (
        f"The Kalshi contract under analysis is `{contract_id}`. "
        "Use this exact contract identifier in every tool call, report, "
        "and recommendation."
    )


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility."""
        messages = state["messages"]

        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


# ---------------------------------------------------------------------------
# Placeholder tool stubs — replaced in Phase 1 with crypto/Kalshi
# implementations under ``tradingagents/dataflows/``.
# ---------------------------------------------------------------------------

_PHASE_1_PENDING = (
    "Tool not yet wired up — Phase 1 of the Kalshi pivot replaces this "
    "placeholder with the real crypto/Kalshi data implementation."
)


@tool
def get_stock_data(
    symbol: Annotated[str, "asset symbol (e.g. BTC)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Placeholder — Phase 1 will implement Coinbase OHLCV fetch."""
    return _PHASE_1_PENDING


@tool
def get_indicators(
    symbol: Annotated[str, "asset symbol (e.g. BTC)"],
    indicator: Annotated[str, "technical indicator name"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """Placeholder — Phase 1 will compute indicators on Coinbase candles."""
    return _PHASE_1_PENDING


@tool
def get_news(
    query: Annotated[str, "search query (asset, keyword, contract id)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Placeholder — Phase 1 will aggregate crypto news RSS feeds."""
    return _PHASE_1_PENDING


@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
) -> str:
    """Placeholder — Phase 1 will pull macro/global crypto headlines."""
    return _PHASE_1_PENDING
