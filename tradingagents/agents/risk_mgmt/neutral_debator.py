from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_risk_debate_summary,
)


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        research_packet = build_research_packet(state)
        risk_summary = get_risk_debate_summary(state)
        trader_decision = state["trader_investment_plan"]

        prompt = f"""You are a Senior Portfolio Strategist acting as the Neutral Risk Analyst. Your objective is to provide a clinically balanced assessment of the trader's plan, weighing growth potential against risk constraints.

Trader's Decision: {trader_decision}

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives ("massive", "huge", "significant"). Every claim must reference a specific number, date, or source.
- NO conversational filler, roleplay, or first-person perspective.
- Prioritize objective synthesis, diversification benefits, and regime alignment.
- Critique both aggressive and conservative positions for data gaps or extreme biases.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim based on data recency and source quality. HIGH = verified from pre-loaded data or tools. MED = inferred from partial evidence. LOW = directional estimate.

CORE ANALYTICAL VECTORS:
1. **Balanced Delta**: Quantitative analysis of trade-offs between growth and stability.
2. **Diversification Efficacy**: Assessment of how the plan fits broader portfolio and market trends.
3. **Neutral Rebuttal**: State the single strongest data point from the opposing argument. Then explain why your thesis holds despite it, using evidence from the research packet.

RESOURCES:
- Compressed research packet: {research_packet}
- Rolling risk summary: {risk_summary}
- Conversation History: {history}
- Last Aggressive Argument: {current_aggressive_response}
- Last Conservative Argument: {current_conservative_response}

Synthesize these into a clinical neutral risk thesis. Focus on identifying the most reliable outcome path based on current evidence.
"""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            **risk_debate_state,
            "history": history + "\n" + argument,
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
