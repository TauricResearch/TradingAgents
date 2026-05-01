"""Macro Summary Agent.

Pure-reasoning LLM node (no tools). Reads the macro scan output and compresses
it into a concise 1-page regime brief, injecting past macro regime memory.

Pattern: ``create_macro_summary_agent(llm, macro_memory)`` → closure
(mirrors macro_synthesis pattern).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.portfolio.portfolio_states import PortfolioManagerState

if TYPE_CHECKING:
    from tradingagents.memory.macro_memory import MacroMemory

logger = logging.getLogger(__name__)


def _build_candidate_context(scan_summary: dict, limit: int = 5) -> str:
    """Build a stable, compact candidate block for PM-facing macro briefs."""
    rows: list[str] = []
    for candidate in scan_summary.get("stocks_to_investigate", [])[:limit]:
        if not isinstance(candidate, dict):
            continue
        catalysts = ", ".join(candidate.get("key_catalysts", [])[:2]) or "None"
        risks = ", ".join(candidate.get("risks", [])[:2]) or "None"
        rows.append(
            " | ".join(
                [
                    str(candidate.get("ticker", "?")),
                    str(candidate.get("conviction", "?")),
                    str(candidate.get("thesis_angle", "?")),
                    f"catalysts: {catalysts}",
                    f"risks: {risks}",
                ]
            )
        )
    return "\n".join(f"- {row}" for row in rows) or "None"


def create_macro_summary_agent(
    llm: Any, macro_memory: MacroMemory | None = None
) -> Callable[[PortfolioManagerState], dict[str, Any]]:
    """Create a macro summary agent node.

    Args:
        llm: A LangChain chat model instance (deep_think recommended).
        macro_memory: Optional MacroMemory instance for regime history injection
            and post-call persistence. When None, memory features are skipped.

    Returns:
        A node function ``macro_summary_node(state)`` compatible with LangGraph.
    """

    def macro_summary_node(state: PortfolioManagerState) -> dict[str, Any]:
        scan_summary = state.get("scan_summary") or {}

        # Hard sentinel: if scan data is absent or only contains an error, return the "NO DATA
        # AVAILABLE" marker immediately without invoking the LLM.  pm_decision_agent checks for
        # this string to apply its conservative-posture override (hold positions, avoid new buys).
        if not scan_summary or (
            isinstance(scan_summary, dict) and scan_summary.keys() == {"error"}
        ):
            error_detail = (
                scan_summary.get("error", "N/A") if isinstance(scan_summary, dict) else "missing"
            )
            raise RuntimeError(
                f"macro_summary_agent: scan_summary missing or contains only error — "
                f"cannot produce macro brief without valid scan data (error: {error_detail})"
            )

        # ------------------------------------------------------------------
        # Compress scan data to save tokens
        # ------------------------------------------------------------------
        executive_summary: str = scan_summary.get("executive_summary", "Not available")

        macro_context: dict = scan_summary.get("macro_context", {})
        macro_context_str = (
            f"Economic cycle: {macro_context.get('economic_cycle', 'N/A')}\n"
            f"Central bank stance: {macro_context.get('central_bank_stance', 'N/A')}\n"
            f"Geopolitical risks: {macro_context.get('geopolitical_risks', 'N/A')}"
        )

        key_themes: list = scan_summary.get("key_themes", [])
        key_themes_str = (
            "\n".join(
                f"- {t.get('theme', '?')} [{t.get('conviction', '?')}] "
                f"({t.get('timeframe', '?')}): {t.get('description', '')}"
                for t in key_themes
            )
            or "None"
        )

        ticker_conviction_str = _build_candidate_context(scan_summary)

        risk_factors: list = scan_summary.get("risk_factors", [])
        risk_factors_str = "\n".join(f"- {r}" for r in risk_factors) or "None"

        # ------------------------------------------------------------------
        # Past macro regime history
        # ------------------------------------------------------------------
        if macro_memory is not None:
            analysis_date = str(state.get("analysis_date") or "").strip()
            if not analysis_date:
                raise RuntimeError(
                    "macro_summary_agent: missing analysis_date/as_of_date context "
                    "for memory lookup"
                )
            past_context = macro_memory.build_macro_context(limit=3, as_of_date=analysis_date)
        else:
            past_context = "No prior macro regime history available."

        # ------------------------------------------------------------------
        # Build system message
        # ------------------------------------------------------------------
        system_message = (
            "You are a Senior Macro Strategist and Systems Architect compressing research into a clinical regime brief.\n\n"
            "STRICT CONSTRAINTS:\n"
            "- Output ONLY a structured clinical brief.\n"
            "- NO conversational filler, roleplay, preamble, or internal monologue/<think> blocks.\n"
            "- Do NOT include any 'thinking' process; provide only the final result.\n"
            "- Retain all exact numeric values (VIX, %, yield, weightings).\n\n"
            "## Past Macro Regime History\n"
            f"{past_context}\n\n"
            "## Current Scan Data\n"
            "### Executive Summary\n"
            f"{executive_summary}\n\n"
            "### Macro Context\n"
            f"{macro_context_str}\n\n"
            "### Key Themes\n"
            f"{key_themes_str}\n\n"
            "### Candidate Tickers (conviction only)\n"
            f"{ticker_conviction_str}\n\n"
            "### Risk Factors\n"
            f"{risk_factors_str}\n\n"
            "Produce the structured macro brief in this exact format:\n\n"
            "MACRO REGIME: [risk-on|risk-off|neutral|transition]\n\n"
            "KEY NUMBERS: [list ALL exact numeric values from input]\n\n"
            "TOP 3 THEMES:\n"
            "1. [theme]: [clinical quantitative description, approx. 30 - 40 words]\n"
            "2. [theme]: [clinical quantitative description, approx. 30 - 40 words]\n"
            "3. [theme]: [clinical quantitative description, approx. 30 - 40 words]\n\n"
            "MACRO-ALIGNED TICKERS: [list high-conviction tickers with quantitative fit rationale, approx. 20 - 30 words per ticker]\n\n"
            "REGIME MEMORY NOTE: [clinical lesson from past history applicable to current deltas, approx. 40 - 50 words]\n"
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
        prompt = prompt.partial(current_date=state.get("analysis_date", ""))

        chain = prompt | llm
        result = chain.invoke([])
        macro_brief = str(getattr(result, "content", "") or "")
        if not macro_brief.strip():
            raise RuntimeError(
                "macro_summary_agent: empty LLM response — cannot produce macro brief"
            )

        # ------------------------------------------------------------------
        # Persist macro regime call to memory
        # ------------------------------------------------------------------
        if macro_memory is not None:
            _persist_regime(macro_brief, scan_summary, macro_memory, state)

        return {
            "messages": [result],
            "macro_brief": macro_brief,
            "macro_memory_context": past_context,
            "sender": "macro_summary_agent",
        }

    return macro_summary_node


def _persist_regime(
    brief: str,
    scan_summary: dict,
    macro_memory: MacroMemory,
    state: dict,
) -> None:
    """Extract MACRO REGIME line and persist to MacroMemory.

    Fails silently — memory persistence must never break the pipeline.
    """
    try:
        macro_call = "neutral"
        match = re.search(r"MACRO REGIME:\s*([^\n]+)", brief, re.IGNORECASE)
        if match:
            raw_call = match.group(1).strip().lower()
            # Normalise to one of the four valid values
            for valid in ("risk-on", "risk-off", "transition", "neutral"):
                if valid in raw_call:
                    macro_call = valid
                    break

        # Best-effort VIX extraction — scan data rarely includes a bare float
        vix_level = 0.0
        vix_match = re.search(r"VIX[:\s]+([0-9]+(?:\.[0-9]+)?)", brief, re.IGNORECASE)
        if vix_match:
            try:
                vix_level = float(vix_match.group(1))
            except ValueError:
                pass

        key_themes = [
            t.get("theme", "") for t in scan_summary.get("key_themes", []) if t.get("theme")
        ]
        sector_thesis = scan_summary.get("executive_summary", "")[:500]
        analysis_date = state.get("analysis_date", "")

        macro_memory.record_macro_state(
            date=analysis_date,
            vix_level=vix_level,
            macro_call=macro_call,
            sector_thesis=sector_thesis,
            key_themes=key_themes,
            run_id=state.get("run_id"),
        )
    except Exception:
        logger.error("macro_summary_agent: failed to persist regime to memory", exc_info=True)
