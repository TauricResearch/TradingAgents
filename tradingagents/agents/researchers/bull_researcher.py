from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_investment_debate_summary,
)


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        research_packet = build_research_packet(state)
        debate_summary = get_investment_debate_summary(state)

        curr_situation = research_packet
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""You are a Senior Quantitative Analyst and Economist building a clinical bull case for the stock. Your objective is to present a data-dense, objective argument for investment based on fundamental and technical delta-changes.

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives ("massive", "huge", "significant"). Every claim must reference a specific number, date, or source.
- NO conversational filler, roleplay, or first-person perspective (e.g., "I believe", "Leans forward").
- Focus strictly on objective data: growth projections, competitive moats, and validated catalysts.
- Address bear counterpoints using hard numbers and logic, not rhetoric.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim based on data recency and source quality. HIGH = verified from pre-loaded data or tools. MED = inferred from partial evidence. LOW = directional estimate.

CORE ANALYTICAL VECTORS:
1. **Growth Delta**: Quantitative revenue/margin projections and addressable market expansion.
2. **Competitive Edge**: Structural moats (unit economics, network effects, IP) backed by evidence.
3. **Execution Signal**: Recent financial health improvements or positive guidance shifts.
4. **Bear Rebuttal**: State the single strongest data point from the opposing argument. Then explain why your thesis holds despite it, using evidence from the research packet.

RESOURCES:
- Compressed research packet: {research_packet}
- Rolling debate summary: {debate_summary}
- Last bear argument: {current_response}
- Historical lessons: {past_memory_str}

Synthesize these into a clinical bull thesis. Address past mistakes by ensuring current evidence is validated against historical outcomes.
"""

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            **investment_debate_state,
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
