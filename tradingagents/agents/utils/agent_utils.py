from typing import Any, Mapping

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


def use_compact_analysis_prompt() -> bool:
    """Return whether analysts should use shorter prompts/reports.

    This is helpful for OpenAI-compatible or Anthropic-compatible backends
    that support the API surface but struggle with the repository's original,
    very verbose analyst instructions.
    """
    from tradingagents.dataflows.config import get_config

    mode = str(get_config().get("analysis_prompt_style", "standard")).strip().lower()
    return mode in {"compact", "fast", "minimax"}


def truncate_prompt_text(text: str, max_chars: int = 1200) -> str:
    """Trim long reports/history before feeding them into compact prompts."""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[truncated]..."


def build_optional_decision_context(
    portfolio_context: str | None,
    peer_context: str | None,
    *,
    peer_context_mode: str = "UNSPECIFIED",
    max_chars: int = 700,
) -> str:
    sections: list[str] = []
    if str(portfolio_context or "").strip():
        sections.append(
            f"Portfolio context: {truncate_prompt_text(str(portfolio_context), max_chars)}"
        )
    if str(peer_context or "").strip():
        mode = str(peer_context_mode or "UNSPECIFIED").strip().upper()
        if mode == "SAME_THEME_NORMALIZED":
            sections.append(
                "Peer context mode: SAME_THEME_NORMALIZED. "
                "You may use this context when deciding SAME_THEME_RANK if the evidence is explicit."
            )
            sections.append(
                f"Peer / same-theme context: {truncate_prompt_text(str(peer_context), max_chars)}"
            )
        else:
            sections.append(
                f"Peer context mode: {mode}. This context is not same-theme normalized. "
                "Treat SAME_THEME_RANK as UNKNOWN unless the context itself contains explicit same-theme evidence."
            )
            sections.append(
                f"Peer universe context: {truncate_prompt_text(str(peer_context), max_chars)}"
            )
    return "\n".join(sections)


def summarize_structured_signal(payload: Mapping[str, Any] | None) -> str:
    if not payload:
        return "rating=UNKNOWN"

    parts = [f"rating={payload.get('rating', 'UNKNOWN')}"]
    hold_subtype = payload.get("hold_subtype")
    if hold_subtype and hold_subtype != "N/A":
        parts.append(f"hold_subtype={hold_subtype}")
    entry_style = payload.get("entry_style")
    if entry_style and entry_style != "UNKNOWN":
        parts.append(f"entry_style={entry_style}")
    same_theme_rank = payload.get("same_theme_rank")
    if same_theme_rank and same_theme_rank != "UNKNOWN":
        parts.append(f"same_theme_rank={same_theme_rank}")
    account_fit = payload.get("account_fit")
    if account_fit and account_fit != "UNKNOWN":
        parts.append(f"account_fit={account_fit}")
    return ", ".join(parts)


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


        
