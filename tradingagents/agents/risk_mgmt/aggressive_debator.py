from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_risk_debate_summary,
)


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        research_packet = build_research_packet(state)
        risk_summary = get_risk_debate_summary(state)
        trader_decision = state["trader_investment_plan"]

        prompt = f"""You are a Senior Quantitative Strategist and AI Developer acting as the Aggressive Risk Analyst. Your objective is to clinically analyze high-reward, high-risk opportunities in the trader's plan, focusing on growth deltas and competitive moats.

Trader's Decision: {trader_decision}

STRICT CONSTRAINTS:
- Output only clinical, quantitative analysis in bullet points.
- NO conversational filler, roleplay, or first-person perspective.
- Identify specific asymmetric upside opportunities and innovative benefits.
- Directly refute conservative/neutral points using hard data and quantitative reasoning.

CORE ANALYTICAL VECTORS:
1. **Upside Delta**: Quantitative analysis of potential growth and innovative benefits.
2. **Moat Validation**: Evidence of structural advantages that justify elevated risk.
3. **Risk-Reward Synthesis**: Data-driven rebuttal of the last conservative and neutral arguments.

RESOURCES:
- Compressed Research: {research_packet}
- Rolling Risk Summary: {risk_summary}
- Conversation History: {history}
- Last Conservative Argument: {current_conservative_response}
- Last Neutral Argument: {current_neutral_response}

Synthesize these into a clinical aggressive risk thesis. Focus on why the current risk profile is optimal for outperforming market norms.
"""

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            **risk_debate_state,
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
