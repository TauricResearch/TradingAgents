from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)


def _create_debator(llm, role: str, prompt_template: str):
    def node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        instrument_context = get_instrument_context_from_state(state)
        trader_decision = state["trader_investment_plan"]

        prompt = prompt_template.format(
            trader_decision=trader_decision,
            instrument_context=instrument_context,
            market_research_report=market_research_report,
            sentiment_report=sentiment_report,
            news_report=news_report,
            fundamentals_report=fundamentals_report,
            history=history,
            current_aggressive_response=risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            current_conservative_response=risk_debate_state.get(
                "current_conservative_response", ""
            ),
            current_neutral_response=risk_debate_state.get(
                "current_neutral_response", ""
            ),
        ) + get_language_instruction()

        response = llm.invoke(prompt)
        speaker = role.capitalize()
        argument = f"{speaker} Analyst: {response.content}"

        new_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": speaker,
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get(
                "current_conservative_response", ""
            ),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }
        new_state[f"{role}_history"] = (
            risk_debate_state.get(f"{role}_history", "") + "\n" + argument
        )
        new_state[f"current_{role}_response"] = argument

        return {"risk_debate_state": new_state}

    return node
