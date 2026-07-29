from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)


def _create_researcher(llm, role: str, prompt_template: str):
    def node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )

        prompt = prompt_template.format(
            target_label=target_label,
            fundamentals_label=fundamentals_label,
            instrument_context=instrument_context,
            market_research_report=market_research_report,
            sentiment_report=sentiment_report,
            news_report=news_report,
            fundamentals_report=fundamentals_report,
            history=history,
            current_response=investment_debate_state.get("current_response", ""),
        ) + get_language_instruction()

        response = llm.invoke(prompt)
        argument = f"{role.capitalize()} Analyst: {response.content}"

        new_state = {
            "history": history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }
        new_state[f"{role}_history"] = (
            investment_debate_state.get(f"{role}_history", "") + "\n" + argument
        )

        return {"investment_debate_state": new_state}

    return node
