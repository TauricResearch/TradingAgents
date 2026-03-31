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
- Output only clinical, quantitative analysis in bullet points.
- NO conversational filler, roleplay, or first-person perspective (e.g., "I believe", "Leans forward").
- Focus strictly on objective data: growth projections, competitive moats, and validated catalysts.
- Address bear counterpoints using hard numbers and logic, not rhetoric.

CORE ANALYTICAL VECTORS:
1. **Growth Delta**: Quantitative revenue/margin projections and addressable market expansion.
2. **Competitive Edge**: Structural moats (unit economics, network effects, IP) backed by evidence.
3. **Execution Signal**: Recent financial health improvements or positive guidance shifts.
4. **Bear Rebuttal**: Direct, data-driven refutation of the last bear argument using the research packet.

RESOURCES:
- Compressed Research: {research_packet}
- Rolling Debate Summary: {debate_summary}
- Last Bear Argument: {current_response}
- Historical Lessons: {past_memory_str}

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
