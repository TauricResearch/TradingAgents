"""Micro Summary Agent.

Pure-reasoning LLM node (no tools). Compresses holding reviews and ranked
candidates into a 1-page micro brief, injecting per-ticker reflexion memory.

Pattern: ``create_micro_summary_agent(llm, micro_memory)`` → closure
(mirrors macro_synthesis pattern).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.portfolio.portfolio_states import PortfolioManagerState

if TYPE_CHECKING:
    from tradingagents.memory.reflexion import ReflexionMemory

logger = logging.getLogger(__name__)


def _analysis_has_deep_dive(analysis: dict) -> bool:
    """Return True when the analysis contains a completed deep-dive decision."""
    if not isinstance(analysis, dict):
        return False
    status = str(analysis.get("analysis_status") or "").strip().lower()
    if status:
        return status == "completed"
    return bool(str(analysis.get("final_trade_decision") or "").strip())


def _extract_rating(decision_text: str) -> str:
    """Extract the PM-style rating from a saved final_trade_decision string."""
    if not decision_text:
        return ""
    match = re.search(r"rating\s*:\s*([A-Za-z -]+)", decision_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _compact_text_block(text: str, limit: int, *, tail_chars: int | None = None) -> str:
    """Keep both the start and end of long strings within a hard cap."""
    text = str(text or "").strip()
    if not text or len(text) <= limit:
        return text

    marker = "\n...\n"
    tail_chars = tail_chars if tail_chars is not None else min(220, max(80, limit // 3))
    head_chars = max(0, limit - tail_chars - len(marker))
    if head_chars <= 0:
        return text[:limit]
    return f"{text[:head_chars].rstrip()}{marker}{text[-tail_chars:].lstrip()}"


def _analysis_snapshot(analysis: dict) -> dict[str, str]:
    """Build a compact deep-dive snapshot for PM consumption."""
    if not _analysis_has_deep_dive(analysis):
        return {}
    final_decision = str(analysis.get("final_trade_decision") or "").strip()
    return {
        "rating": _extract_rating(final_decision),
        "final_trade_decision": _compact_text_block(final_decision, 900, tail_chars=320),
        "trader_plan": _compact_text_block(
            str(analysis.get("trader_investment_plan") or "").strip(),
            420,
            tail_chars=140,
        ),
        "research_plan": _compact_text_block(
            str(analysis.get("investment_plan") or "").strip(),
            420,
            tail_chars=140,
        ),
        "market_report": _compact_text_block(
            str(analysis.get("market_report") or "").strip(),
            320,
            tail_chars=120,
        ),
        "fundamentals_report": _compact_text_block(
            str(analysis.get("fundamentals_report") or "").strip(),
            320,
            tail_chars=120,
        ),
    }


def _lookup_analysis(ticker_analyses: dict, ticker: str, instrument_key: str = "") -> dict:
    """Find a saved deep-dive analysis by instrument key or bare ticker."""
    if not isinstance(ticker_analyses, dict):
        return {}
    ticker = str(ticker or "").upper()
    keys = [instrument_key, ticker, f"equity:{ticker}"]
    for key in keys:
        if key and isinstance(ticker_analyses.get(key), dict):
            return ticker_analyses[key]
    return {}


def create_micro_summary_agent(
    llm: Any, micro_memory: ReflexionMemory | None = None
) -> Callable[[PortfolioManagerState], dict[str, Any]]:
    """Create a micro summary agent node.

    Args:
        llm: A LangChain chat model instance (mid_think or deep_think recommended).
        micro_memory: Optional ReflexionMemory instance for per-ticker history
            injection. When None, memory features are skipped.

    Returns:
        A node function ``micro_summary_node(state)`` compatible with LangGraph.
    """

    def micro_summary_node(state: PortfolioManagerState) -> dict[str, Any]:
        analysis_date = state.get("analysis_date") or ""

        # ------------------------------------------------------------------
        # Parse inputs — handle missing / malformed gracefully
        # ------------------------------------------------------------------
        holding_reviews_raw = state.get("holding_reviews") or "{}"
        candidates_raw = state.get("prioritized_candidates") or "[]"

        holding_reviews: dict = _parse_json_safely(holding_reviews_raw, default={})
        candidates: list = _parse_json_safely(candidates_raw, default=[])

        if not holding_reviews:
            logger.warning(
                "micro_summary_agent: No holding reviews found in state. Proceeding with partial synthesis."
            )
        if not candidates:
            logger.warning(
                "micro_summary_agent: No prioritized candidates found in state. Proceeding with partial synthesis."
            )

        # Optional: per-ticker trading graph analyses (fundamentals, technicals, etc.)
        ticker_analyses: dict = state.get("ticker_analyses") or {}

        # ------------------------------------------------------------------
        # Collect all tickers and retrieve per-ticker memory
        # ------------------------------------------------------------------
        holding_tickers = list(holding_reviews.keys()) if isinstance(holding_reviews, dict) else []
        candidate_tickers = [
            c.get("ticker", "") for c in candidates if isinstance(c, dict) and c.get("ticker")
        ]
        all_tickers = list(
            dict.fromkeys(holding_tickers + candidate_tickers)
        )  # preserve order, dedupe

        ticker_memory_dict: dict[str, str] = {}
        if micro_memory is not None:
            for ticker in all_tickers:
                ticker_memory_dict[ticker] = micro_memory.build_context(ticker, limit=2)

        ticker_memory_str = json.dumps(ticker_memory_dict)
        deep_dive_context: dict[str, dict[str, str]] = {}
        if isinstance(ticker_analyses, dict):
            instrument_keys = {
                str(c.get("ticker") or "").upper(): str(c.get("instrument_key") or "")
                for c in candidates
                if isinstance(c, dict)
            }
            for ticker in all_tickers:
                snapshot = _analysis_snapshot(
                    _lookup_analysis(ticker_analyses, ticker, instrument_keys.get(ticker, ""))
                )
                if snapshot:
                    deep_dive_context[ticker] = snapshot

        # ------------------------------------------------------------------
        # Build concise per-ticker input table
        # ------------------------------------------------------------------
        table_rows: list[str] = []

        for ticker in holding_tickers:
            review = holding_reviews.get(ticker, {}) if isinstance(holding_reviews, dict) else {}
            if not isinstance(review, dict):
                review = {}
            rec = review.get("recommendation", "?")
            confidence = review.get("confidence", "")
            label = f"HOLDING | {rec} | conf:{confidence}" if confidence else f"HOLDING | {rec}"
            analysis = deep_dive_context.get(ticker, {})
            rating = analysis.get("rating") or "NO DATA"
            key_number = f"rating:{rating}"
            memory_snippet = ticker_memory_dict.get(ticker, "")[:100] or "no memory"
            table_rows.append(f"{ticker} | {label} | {key_number} | {memory_snippet}")

        for c in candidates:
            if not isinstance(c, dict):
                continue
            ticker = c.get("ticker", "?")
            conviction = c.get("conviction", "?")
            thesis = c.get("thesis_angle", "?")
            priority_score = c.get("priority_score", "")
            analysis = deep_dive_context.get(ticker, {})
            rating = analysis.get("rating", "")
            score_text = (
                f"priority_score:{priority_score}"
                if priority_score != ""
                else "priority_score:NO DATA"
            )
            key_number = f"{score_text} | rating:{rating}" if rating else score_text
            label = f"CANDIDATE | {conviction} | {thesis}"
            memory_snippet = ticker_memory_dict.get(ticker, "")[:100] or "no memory"
            table_rows.append(f"{ticker} | {label} | {key_number} | {memory_snippet}")

        ticker_table = "\n".join(table_rows) or "No tickers available."

        # Serialise full detail for LLM context
        holding_reviews_str = (
            json.dumps(holding_reviews, indent=2)
            if holding_reviews
            else "No holding reviews available."
        )
        candidates_str = (
            json.dumps(candidates, indent=2) if candidates else "No candidates available."
        )
        deep_dive_str = (
            json.dumps(deep_dive_context, indent=2)
            if deep_dive_context
            else "No completed deep-dive ticker analyses available."
        )

        # ------------------------------------------------------------------
        # Build system message
        # ------------------------------------------------------------------
        system_message = (
            "You are a Senior Portfolio Strategist and Systems Architect compressing position-level data into a clinical brief.\n\n"
            "## Per-Ticker Data\n"
            f"{ticker_table}\n\n"
            "## Completed Deep Dive Analyses\n"
            f"{deep_dive_str}\n\n"
            "## Holding Reviews\n"
            f"{holding_reviews_str}\n\n"
            "## Prioritized Candidates\n"
            f"{candidates_str}\n\n"
            "STRICT CONSTRAINTS:\n"
            "- Output ONLY a structured clinical brief.\n"
            "- NO conversational filler, roleplay, or preamble.\n"
            "- Retain all exact numeric values (debt ratios, P/E, EPS, P&L %).\n\n"
            "Produce the structured micro brief in this exact format:\n\n"
            "HOLDINGS TABLE:\n"
            "| TICKER | ACTION | KEY NUMBER | FLAG | MEMORY |\n"
            "|--------|--------|------------|------|--------|\n"
            '[one row per holding — use "NO DATA" if missing]\n\n'
            "CANDIDATES TABLE:\n"
            "| TICKER | CONVICTION | THESIS ANGLE | KEY NUMBER | FLAG | MEMORY |\n"
            "|--------|------------|--------------|------------|------|--------|\n"
            '[one row per candidate — use "NO DATA" if missing]\n\n'
            "RED FLAGS: [clinical list of accounting anomalies, leverage breaches, or losses with exact numbers]\n"
            "GREEN FLAGS: [clinical list of momentum leads, insider buying, or positive memory with exact numbers]\n"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names="none")
        prompt = prompt.partial(current_date=analysis_date)

        chain = prompt | llm
        result = chain.invoke([])

        return {
            "messages": [result],
            "micro_brief": result.content,
            "micro_memory_context": ticker_memory_str,
            "sender": "micro_summary_agent",
        }

    return micro_summary_node


def _parse_json_safely(raw: str, *, default: Any) -> Any:
    """Parse a JSON string, returning *default* on any parse error.

    Args:
        raw:     Raw string (may be JSON or empty/malformed).
        default: Value to return when parsing fails.
    """
    if not raw or not raw.strip():
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "micro_summary_agent: could not parse JSON input (first 100): %s",
            raw[:100],
        )
        return default
