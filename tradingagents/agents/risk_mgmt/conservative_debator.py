from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_risk_debate_summary,
)


def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        research_packet = build_research_packet(state)
        risk_summary = get_risk_debate_summary(state)
        trader_decision = state["trader_investment_plan"]

        prompt = f"""You are a Senior Risk Manager and Economist acting as the Conservative Risk Analyst. Your objective is to clinically identify systemic risks, volatility threats, and capital preservation requirements in the trader's plan.

Trader's Decision: {trader_decision}

STRICT CONSTRAINTS:
- Output only clinical, quantitative analysis in bullet points.
- NO conversational filler, roleplay, or first-person perspective.
- Prioritize asset protection, volatility minimization, and tail-risk assessment.
- Directly refute aggressive/neutral optimism using quantitative risk metrics and historical parallels.

CORE ANALYTICAL VECTORS:
1. **Risk Exposure**: Quantitative assessment of potential drawdowns and market volatility.
2. **Structural Fragility**: Identification of overlooked threats or unsustainable assumptions in the plan.
3. **Defensive Synthesis**: Data-driven rebuttal of the last aggressive and neutral arguments.

RESOURCES:
- Compressed Research: {research_packet}
- Rolling Risk Summary: {risk_summary}
- Conversation History: {history}
- Last Aggressive Argument: {current_aggressive_response}
- Last Neutral Argument: {current_neutral_response}

Synthesize these into a clinical conservative risk thesis. Focus on why capital preservation must take precedence in the current regime.
"""

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            **risk_debate_state,
            "history": history + "\n" + argument,
            "conservative_history": conservative_history + "\n" + argument,
            "latest_speaker": "Conservative",
            "current_conservative_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
