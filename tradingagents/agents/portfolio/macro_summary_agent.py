"""Macro Summary Agent.

Pure-reasoning LLM node (no tools). Reads the macro scan output and compresses
it into a concise 1-page regime brief, injecting past macro regime memory.

Pattern: ``create_macro_summary_agent(llm, macro_memory)`` → closure
(mirrors macro_synthesis pattern).
"""

from __future__ import annotations

import json
import logging
import re

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.memory.macro_memory import MacroMemory

logger = logging.getLogger(__name__)


def create_macro_summary_agent(llm, macro_memory: MacroMemory | None = None):
    """Create a macro summary agent node.

    Args:
        llm: A LangChain chat model instance (deep_think recommended).
        macro_memory: Optional MacroMemory instance for regime history injection
            and post-call persistence. When None, memory features are skipped.

    Returns:
        A node function ``macro_summary_node(state)`` compatible with LangGraph.
    """

    def macro_summary_node(state: dict) -> dict:
        scan_summary = state.get("scan_summary") or {}

        # Guard: abort early if scan data is absent or *only* contains an error
        # (partial failures with real data + an "error" key are still usable)
        if not scan_summary or (isinstance(scan_summary, dict) and scan_summary.keys() == {"error"}):
            return {
                "messages": [],
                "macro_brief": "NO DATA AVAILABLE - ABORT MACRO",
                "macro_memory_context": "",
                "sender": "macro_summary_agent",
            }

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
        key_themes_str = "\n".join(
            f"- {t.get('theme', '?')} [{t.get('conviction', '?')}] "
            f"({t.get('timeframe', '?')}): {t.get('description', '')}"
            for t in key_themes
        ) or "None"

        # Strip verbose rationale — retain only what the brief needs
        ticker_conviction = [
            {
                "ticker": t.get("ticker", "?"),
                "conviction": t.get("conviction", "?"),
                "thesis_angle": t.get("thesis_angle", "?"),
            }
            for t in scan_summary.get("stocks_to_investigate", [])
        ]
        ticker_conviction_str = json.dumps(ticker_conviction, indent=2) or "[]"

        risk_factors: list = scan_summary.get("risk_factors", [])
        risk_factors_str = "\n".join(f"- {r}" for r in risk_factors) or "None"

        # ------------------------------------------------------------------
        # Past macro regime history
        # ------------------------------------------------------------------
        if macro_memory is not None:
            past_context = macro_memory.build_macro_context(limit=3)
        else:
            past_context = "No prior macro regime history available."

        # ------------------------------------------------------------------
        # Build system message
        # ------------------------------------------------------------------
        system_message = (
            "You are a macro strategist compressing a scanner report into a concise regime brief.\n\n"
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
            "Produce a structured macro brief in this exact format:\n\n"
            "MACRO REGIME: [risk-on|risk-off|neutral|transition]\n\n"
            "KEY NUMBERS: [retain ALL exact numeric values — VIX levels, %, yield values, "
            "sector weightings — do not round or omit]\n\n"
            "TOP 3 THEMES:\n"
            "1. [theme]: [description — retain all numbers]\n"
            "2. [theme]: [description — retain all numbers]\n"
            "3. [theme]: [description — retain all numbers]\n\n"
            "MACRO-ALIGNED TICKERS: [list tickers with high conviction and why they fit the regime]\n\n"
            "REGIME MEMORY NOTE: [any relevant lesson from past macro history that applies now]\n\n"
            "IMPORTANT: Do NOT restrict yourself to a word count. Retain every numeric value from the "
            "scan data. If the scan data is incomplete, note it explicitly — do not guess or extrapolate."
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
        result = chain.invoke(state["messages"])

        # ------------------------------------------------------------------
        # Persist macro regime call to memory
        # ------------------------------------------------------------------
        if macro_memory is not None:
            _persist_regime(result.content, scan_summary, macro_memory, state)

        return {
            "messages": [result],
            "macro_brief": result.content,
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
        )
    except Exception:
        logger.warning("macro_summary_agent: failed to persist regime to memory", exc_info=True)
