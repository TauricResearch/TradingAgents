
from tradingagents.agents.utils.agent_utils import (
    DEBATE_EVIDENCE_GUARDRAIL,
    build_capital_context,
    get_language_instruction,
    truncate_history,
)


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = truncate_history(risk_debate_state.get("history", ""))
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        trader_decision = state["trader_investment_plan"]
        capital_context = build_capital_context(state.get("holdings_info"))
        capital_block = f"\n\n{capital_context}" if capital_context else ""

        prompt = f"""You are the Neutral Risk Analyst. Provide a balanced assessment of the trader's decision, challenging both the aggressive and conservative arguments where each is one-sided. Speak conversationally.

Trader's decision: {trader_decision}{capital_block}

Debate history: {history}
Last aggressive argument: {current_aggressive_response}
Last conservative argument: {current_conservative_response}{DEBATE_EVIDENCE_GUARDRAIL}{get_language_instruction()}"""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": risk_debate_state.get("history", "") + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
