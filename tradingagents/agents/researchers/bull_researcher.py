from langchain_core.messages import AIMessage

from tradingagents.agents.utils.anonymization import anonymize_ticker
from tradingagents.agents.utils.llm_guard import invoke_with_timeout, truncate_text
from tradingagents.agents.utils.summary_context import (
    build_debate_evidence_brief,
    build_investment_debate_summary,
    build_research_packet,
    get_investment_debate_summary,
)
from tradingagents.default_config import DEFAULT_CONFIG


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        ticker = state["company_of_interest"]
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        evidence_brief = build_debate_evidence_brief(state)
        research_packet = build_research_packet(state)
        debate_summary = get_investment_debate_summary(state)

        curr_situation = research_packet
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for _i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        # Anonymize data variables to prevent training-data bias
        is_round2 = investment_debate_state.get("count", 0) >= 2
        anon_research_packet = anonymize_ticker(
            truncate_text(evidence_brief, max_chars=2000), ticker
        )
        anon_debate_summary = anonymize_ticker(
            truncate_text(debate_summary, max_chars=1800), ticker
        )
        # Round 2: rely on rolling summary only, skip raw history to cut tokens
        anon_history = "" if is_round2 else anonymize_ticker(
            truncate_text(history, max_chars=1200), ticker
        )
        anon_current_response = anonymize_ticker(
            truncate_text(current_response, max_chars=800), ticker
        )
        anon_past_memory_str = anonymize_ticker(
            truncate_text(past_memory_str, max_chars=1600), ticker
        )

        prompt = f"""You are a Senior Quantitative Analyst building a clinical bull case for the stock.

STRICT CONSTRAINTS:
- Cite exact values: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives. Every claim needs a specific number.
- NO conversational filler, roleplay, or first-person perspective.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim. HIGH = verified data. MED = partial evidence. LOW = directional estimate.

RESOURCES:
- Compressed Research: {anon_research_packet}
- Rolling Debate Summary: {anon_debate_summary}
- Debate History: {anon_history}
- Last Bear Argument: {anon_current_response}
- Historical Lessons: {anon_past_memory_str}

OUTPUT FORMAT (follow exactly — no prose, no extra sections):

CLAIMS:
- [HIGH/MED/LOW] Growth delta claim with exact numbers
- [HIGH/MED/LOW] Competitive edge or execution signal claim with exact numbers
- [HIGH/MED/LOW] Third strongest bullish data point with exact numbers

COUNTERPOINT: State the single strongest bear data point from opponent's argument.
REBUTTAL: Why your thesis holds despite it — one line, hard numbers only.

SIGNAL: supports_buy | supports_hold | neutral

Rules: Exactly 3 claims max. One counterpoint. One rebuttal. No paragraphs.
"""

        _cap = float(DEFAULT_CONFIG.get("mid_think_llm_timeout_cap") or 240.0)
        timeout_seconds = min(
            float(DEFAULT_CONFIG.get("mid_think_llm_timeout") or DEFAULT_CONFIG.get("llm_timeout") or _cap),
            _cap,
        )
        response, invoke_error = invoke_with_timeout(
            llm,
            prompt,
            timeout_seconds=timeout_seconds,
            max_tokens=DEFAULT_CONFIG.get("mid_think_llm_max_tokens"),
        )
        if invoke_error is not None:
            if isinstance(invoke_error, TimeoutError):
                response = AIMessage(
                    content=(
                        "CLAIMS:\n"
                        f"- [LOW] Bull researcher timed out after {timeout_seconds:.0f}s; no new bullish claims this round\n"
                        "- [LOW] Reuse validated growth/moat/catalyst evidence from prior analyst reports\n"
                        "- [LOW] Escalate with current packet and existing debate state\n\n"
                        "COUNTERPOINT: N/A (timeout)\n"
                        "REBUTTAL: N/A (timeout)\n\n"
                        "SIGNAL: neutral"
                    )
                )
            else:
                raise invoke_error

        argument = f"Bull Analyst: {response.content}"

        # Extract claims for fast aggregation (supports both new CLAIMS: and legacy SUMMARY POINTS:)
        summary_section = ""
        if "CLAIMS:" in response.content:
            summary_section = response.content.split("CLAIMS:")[-1].strip()
            # Trim at COUNTERPOINT if present to get only the claims
            if "COUNTERPOINT:" in summary_section:
                summary_section = summary_section.split("COUNTERPOINT:")[0].strip()
        elif "SUMMARY POINTS:" in response.content:
            summary_section = response.content.split("SUMMARY POINTS:")[-1].strip()

        current_bull_summary = summary_section or str(
            investment_debate_state.get("current_bull_summary") or ""
        ).strip()
        next_summary = build_investment_debate_summary(
            {
                **investment_debate_state,
                "current_bull_summary": current_bull_summary,
            }
        )
        if not next_summary:
            next_summary = str(investment_debate_state.get("summary") or "").strip()

        new_investment_debate_state = {
            **investment_debate_state,
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "current_response": argument,
            "current_bull_summary": current_bull_summary,
            "summary": next_summary,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
