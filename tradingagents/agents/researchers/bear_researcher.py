from tradingagents.agents.utils.anonymization import anonymize_ticker
from tradingagents.agents.utils.llm_guard import invoke_with_timeout, truncate_text
from tradingagents.agents.utils.summary_context import (
    build_investment_debate_summary,
    build_research_packet,
    get_investment_debate_summary,
)
from tradingagents.default_config import DEFAULT_CONFIG
from langchain_core.messages import AIMessage


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        ticker = state["company_of_interest"]
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        research_packet = build_research_packet(state)
        debate_summary = get_investment_debate_summary(state)

        curr_situation = research_packet
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        # Anonymize data variables to prevent training-data bias
        anon_research_packet = anonymize_ticker(
            truncate_text(research_packet, max_chars=5000), ticker
        )
        anon_debate_summary = anonymize_ticker(
            truncate_text(debate_summary, max_chars=1800), ticker
        )
        anon_history = anonymize_ticker(truncate_text(history, max_chars=2200), ticker)
        anon_current_response = anonymize_ticker(
            truncate_text(current_response, max_chars=1200), ticker
        )
        anon_past_memory_str = anonymize_ticker(
            truncate_text(past_memory_str, max_chars=1600), ticker
        )

        prompt = f"""You are a Senior Quantitative Analyst and Economist building a clinical bear case against the stock. Your objective is to present a data-dense, objective argument for risk avoidance based on fundamental and technical delta-changes.

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives ("massive", "huge", "significant"). Every claim must reference a specific number, date, or source.
- NO conversational filler, roleplay, or first-person perspective (e.g., "I suspect", "Voice tightens").
- Focus strictly on objective data: margin compression, structural headwinds, and validated risks.
- Address bull counterpoints using hard numbers and logic, not rhetoric.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim based on data recency and source quality. HIGH = verified from pre-loaded data or tools. MED = inferred from partial evidence. LOW = directional estimate.

CORE ANALYTICAL VECTORS:
1. **Risk Delta**: Quantitative evidence of financial instability, market saturation, or macro threats.
2. **Competitive Fragility**: Evidence of declining innovation or intensifying competitive pressure.
3. **Negative Indicators**: Adverse news trends or deteriorating financial health metrics.
4. **Bull Rebuttal**: State the single strongest data point from the opposing argument. Then explain why your thesis holds despite it, using evidence from the research packet.

RESOURCES:
- Compressed Research: {anon_research_packet}
- Rolling Debate Summary: {anon_debate_summary}
- Raw Debate History: {anon_history}
- Last Bull Argument: {anon_current_response}
- Historical Lessons: {anon_past_memory_str}

Synthesize these into a clinical bear thesis. Address past mistakes by ensuring current evidence is validated against historical outcomes.

Output your response in two sections:
1. THE DEBATE: Your clinical rebuttal/argument.
2. SUMMARY POINTS: A concise bulleted list of your 3 most critical bearish points for this round.
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
            max_tokens=900,
        )
        if invoke_error is not None:
            if isinstance(invoke_error, TimeoutError):
                response = AIMessage(
                    content=(
                        "THE DEBATE:\n"
                        f"- Bear researcher timed out after {timeout_seconds:.0f}s; no new bearish expansion was added this round.\n"
                        "- Preserve the strongest validated downside evidence already present in the compressed research packet.\n"
                        "- Treat this round as incomplete and avoid adding unsourced bearish claims.\n\n"
                        "SUMMARY POINTS:\n"
                        "- No new bearish claims added due timeout fallback.\n"
                        "- Reuse validated risk, fragility, and headwind evidence from prior analyst reports only.\n"
                        "- Escalate with current packet and existing debate state."
                    )
                )
            else:
                raise invoke_error

        argument = f"Bear Analyst: {response.content}"

        # Extract summary points for fast aggregation
        summary_section = ""
        if "SUMMARY POINTS:" in response.content:
            summary_section = response.content.split("SUMMARY POINTS:")[-1].strip()

        current_bear_summary = summary_section or str(
            investment_debate_state.get("current_bear_summary") or ""
        ).strip()
        next_summary = build_investment_debate_summary(
            {
                **investment_debate_state,
                "current_bear_summary": current_bear_summary,
            }
        )
        if not next_summary:
            next_summary = str(investment_debate_state.get("summary") or "").strip()

        new_investment_debate_state = {
            **investment_debate_state,
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "current_response": argument,
            "current_bear_summary": current_bear_summary,
            "summary": next_summary,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
