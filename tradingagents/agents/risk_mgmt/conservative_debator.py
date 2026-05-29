
from tradingagents.agents.utils.agent_utils import (
    DEBATE_EVIDENCE_GUARDRAIL,
    build_capital_context,
    truncate_history,
    get_language_instruction,
)


def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = truncate_history(risk_debate_state.get("history", ""))
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        trader_decision = state["trader_investment_plan"]
        capital_context = build_capital_context(state.get("holdings_info"))
        capital_block = f"\n\n{capital_context}" if capital_context else ""

        prompt = f"""You are the Conservative Risk Analyst. Critique the trader's decision by highlighting downside risks and countering aggressive/neutral arguments that overlook threats. Speak conversationally.

Trader's decision: {trader_decision}{capital_block}

Debate history: {history}
Last aggressive argument: {current_aggressive_response}
Last neutral argument: {current_neutral_response}{DEBATE_EVIDENCE_GUARDRAIL}{get_language_instruction()}"""

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": risk_debate_state.get("history", "") + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
