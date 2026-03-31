from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_investment_debate_summary,
)


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
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

        prompt = f"""You are a Senior Quantitative Analyst and Economist building a clinical bear case against the stock. Your objective is to present a data-dense, objective argument for risk avoidance based on fundamental and technical delta-changes.

STRICT CONSTRAINTS:
- Output only clinical, quantitative analysis in bullet points.
- NO conversational filler, roleplay, or first-person perspective (e.g., "I suspect", "Voice tightens").
- Focus strictly on objective data: margin compression, structural headwinds, and validated risks.
- Address bull counterpoints using hard numbers and logic, not rhetoric.

CORE ANALYTICAL VECTORS:
1. **Risk Delta**: Quantitative evidence of financial instability, market saturation, or macro threats.
2. **Competitive Fragility**: Evidence of declining innovation or intensifying competitive pressure.
3. **Negative Indicators**: Adverse news trends or deteriorating financial health metrics.
4. **Bull Rebuttal**: Direct, data-driven refutation of the last bull argument using the research packet.

RESOURCES:
- Compressed Research: {research_packet}
- Rolling Debate Summary: {debate_summary}
- Last Bull Argument: {current_response}
- Historical Lessons: {past_memory_str}

Synthesize these into a clinical bear thesis. Address past mistakes by ensuring current evidence is validated against historical outcomes.
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            **investment_debate_state,
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
