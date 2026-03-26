"""Micro Summary Agent.

Pure-reasoning LLM node (no tools). Compresses holding reviews and ranked
candidates into a 1-page micro brief, injecting per-ticker reflexion memory.

Pattern: ``create_micro_summary_agent(llm, micro_memory)`` → closure
(mirrors macro_synthesis pattern).
"""

from __future__ import annotations

import json
import logging

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.memory.reflexion import ReflexionMemory

logger = logging.getLogger(__name__)


def create_micro_summary_agent(llm, micro_memory: ReflexionMemory | None = None):
    """Create a micro summary agent node.

    Args:
        llm: A LangChain chat model instance (mid_think or deep_think recommended).
        micro_memory: Optional ReflexionMemory instance for per-ticker history
            injection. When None, memory features are skipped.

    Returns:
        A node function ``micro_summary_node(state)`` compatible with LangGraph.
    """

    def micro_summary_node(state: dict) -> dict:
        analysis_date = state.get("analysis_date") or ""

        # ------------------------------------------------------------------
        # Parse inputs — handle missing / malformed gracefully
        # ------------------------------------------------------------------
        holding_reviews_raw = state.get("holding_reviews") or "{}"
        candidates_raw = state.get("prioritized_candidates") or "[]"

        holding_reviews: dict = _parse_json_safely(holding_reviews_raw, default={})
        candidates: list = _parse_json_safely(candidates_raw, default=[])

        # Optional: per-ticker trading graph analyses (fundamentals, technicals, etc.)
        ticker_analyses: dict = state.get("ticker_analyses") or {}

        # ------------------------------------------------------------------
        # Collect all tickers and retrieve per-ticker memory
        # ------------------------------------------------------------------
        holding_tickers = list(holding_reviews.keys()) if isinstance(holding_reviews, dict) else []
        candidate_tickers = [
            c.get("ticker", "") for c in candidates if isinstance(c, dict) and c.get("ticker")
        ]
        all_tickers = list(dict.fromkeys(holding_tickers + candidate_tickers))  # preserve order, dedupe

        ticker_memory_dict: dict[str, str] = {}
        if micro_memory is not None:
            for ticker in all_tickers:
                ticker_memory_dict[ticker] = micro_memory.build_context(ticker, limit=2)

        ticker_memory_str = json.dumps(ticker_memory_dict)

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
            # Enrich with trading graph analysis if available
            analysis = ticker_analyses.get(ticker, {}) if isinstance(ticker_analyses, dict) else {}
            key_number = analysis.get("final_trade_decision", "")[:80] if isinstance(analysis, dict) else ""
            key_number = key_number or "-"
            memory_snippet = (ticker_memory_dict.get(ticker, "")[:100] or "no memory")
            table_rows.append(f"{ticker} | {label} | {key_number} | {memory_snippet}")

        for c in candidates:
            if not isinstance(c, dict):
                continue
            ticker = c.get("ticker", "?")
            conviction = c.get("conviction", "?")
            thesis = c.get("thesis_angle", "?")
            score = c.get("score", "")
            key_number = f"score:{score}" if score != "" else "-"
            label = f"CANDIDATE | {conviction} | {thesis}"
            memory_snippet = (ticker_memory_dict.get(ticker, "")[:100] or "no memory")
            table_rows.append(f"{ticker} | {label} | {key_number} | {memory_snippet}")

        ticker_table = "\n".join(table_rows) or "No tickers available."

        # Serialise full detail for LLM context
        holding_reviews_str = (
            json.dumps(holding_reviews, indent=2)
            if holding_reviews
            else "No holding reviews available."
        )
        candidates_str = (
            json.dumps(candidates, indent=2)
            if candidates
            else "No candidates available."
        )

        # ------------------------------------------------------------------
        # Build system message
        # ------------------------------------------------------------------
        system_message = (
            "You are a micro analyst compressing position-level data into a concise brief "
            "for a portfolio manager.\n\n"
            "## Per-Ticker Data\n"
            f"{ticker_table}\n\n"
            "## Holding Reviews (full detail)\n"
            f"{holding_reviews_str}\n\n"
            "## Prioritized Candidates (full detail)\n"
            f"{candidates_str}\n\n"
            "Produce a structured micro brief in this exact format:\n\n"
            "HOLDINGS TABLE:\n"
            "| TICKER | ACTION | KEY NUMBER | FLAG | MEMORY |\n"
            "|--------|--------|------------|------|--------|\n"
            "[one row per holding — if data is missing, write \"NO DATA\" in KEY NUMBER and FLAG columns]\n\n"
            "CANDIDATES TABLE:\n"
            "| TICKER | CONVICTION | THESIS ANGLE | KEY NUMBER | FLAG | MEMORY |\n"
            "|--------|------------|--------------|------------|------|--------|\n"
            "[one row per candidate — if data is missing, write \"NO DATA\"]\n\n"
            "RED FLAGS: [list any tickers with accounting anomalies, high debt, or historical losses "
            "— cite exact numbers]\n"
            "GREEN FLAGS: [list tickers with strong momentum, insider buying, or positive memory "
            "— cite exact numbers]\n\n"
            "IMPORTANT: Retain exact debt ratios, P/E multiples, EPS values, and unrealized P&L "
            "percentages. Never round or omit a numeric value. If a ticker has no data, write "
            "\"NO DATA\" — do not guess."
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
        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "micro_brief": result.content,
            "micro_memory_context": ticker_memory_str,
            "sender": "micro_summary_agent",
        }

    return micro_summary_node


def _parse_json_safely(raw: str, *, default):
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
