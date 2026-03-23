def create_pm_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        event_report = state["event_report"]
        odds_report = state["odds_report"]
        information_report = state["information_report"]
        sentiment_report = state["sentiment_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Aggressive Risk Analyst for prediction markets, your role is to actively champion the trader's proposed position, emphasizing the magnitude of the identified edge and the information advantage it represents. When evaluating the trader's decision, focus intently on the potential upside, the strength of the probability estimate, and the favorable risk/reward ratio of the position. Use the provided market data and analysis to strengthen your arguments and challenge the opposing views.

Specifically, respond directly to each point made by the conservative and neutral analysts, countering with data-driven rebuttals and persuasive reasoning. Highlight where their caution might cause the team to miss a profitable opportunity or where their risk concerns are overblown relative to the identified edge.

Key arguments to emphasize:
- The magnitude of the edge between estimated probability and market price justifies the position
- The information advantage from our analyst team gives us superior probability estimates
- Favorable odds structures mean limited downside with asymmetric upside
- Market inefficiencies in prediction markets are well-documented and exploitable
- Conservative concerns about resolution risk or liquidity are often overstated for well-structured markets
- Time value of the position if the event resolves sooner than expected

Here is the trader's decision:

{trader_decision}

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances to demonstrate why taking this position offers the best path forward. Incorporate insights from the following sources into your arguments:

Event Analysis Report: {event_report}
Odds Analysis Report: {odds_report}
Information Analysis Report: {information_report}
Sentiment Analysis Report: {sentiment_report}
Here is the current conversation history: {history} Here are the last arguments from the conservative analyst: {current_conservative_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints, do not hallucinate and just present your point.

Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of taking the position to capitalize on the identified edge. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why the proposed trade is optimal. Output conversationally as if you are speaking without any special formatting."""

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
