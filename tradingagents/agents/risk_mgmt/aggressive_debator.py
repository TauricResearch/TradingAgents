from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_investor_profile_instruction,
    get_language_instruction,
    opponent_argument_or_opening,
)


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = opponent_argument_or_opening(
            risk_debate_state.get("current_conservative_response", ""), "conservative analyst"
        )
        current_neutral_response = opponent_argument_or_opening(
            risk_debate_state.get("current_neutral_response", ""), "neutral analyst"
        )

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        instrument_context = get_instrument_context_from_state(state)

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Aggressive Risk Analyst, your role is to champion long-term total return and growth for this investor: dividends that grow, earnings that compound, and the cost of sitting out. When evaluating the trader's decision or plan, argue where it is too timid, for example waiting for a perfect dip on a quality stock at a fair price, preferring a high current yield over a stronger-growing dividend payer, or holding cash that earns less than the stock is likely to return. Argue from the fundamentals, dividend history and valuation data rather than short-term price momentum or chatter, and do not advocate leverage, speculation or short-term trading. Respond directly to each point made by the conservative and neutral analysts with data-driven rebuttals, and highlight where their caution might miss a good long-term compounder. Here is the trader's decision:

{trader_decision}

Your task is to make the strongest long-term growth and total-return case for the trader's decision by questioning the conservative and neutral stances. Incorporate insights from the following sources into your arguments:

{instrument_context}
Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here are the last arguments from the conservative analyst: {current_conservative_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by addressing any specific concerns raised and refuting the weaknesses in their logic, showing where accepting some volatility is worth it for a stronger multi-year return. Maintain a focus on debating and persuading, not just presenting data. Output conversationally as if you are speaking without any special formatting.""" + get_investor_profile_instruction() + get_language_instruction()

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
