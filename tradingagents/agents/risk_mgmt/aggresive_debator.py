import time
import json


def create_risky_debator(llm):
    def risky_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        risky_history = risk_debate_state.get("risky_history", "")

        current_safe_response = risk_debate_state.get("current_safe_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Risky Risk Analyst for SHORT-TERM trading (1-2 week horizon), your role is to actively champion high-reward opportunities that can be captured in the next 1-2 weeks. When evaluating the trader's position decision (LONG/SHORT/HOLD), focus intently on near-term catalysts, momentum, and short-term upside potential—even when these come with elevated risk. Use the provided market data and sentiment analysis to strengthen your arguments for aggressive short-term positioning. Specifically, respond directly to each point made by the conservative and neutral analysts, countering with data-driven rebuttals focused on short-term opportunities. Highlight where their caution might miss critical near-term opportunities. Here is the trader's position decision:

{trader_decision}

Your task is to create a compelling case for an aggressive SHORT-TERM position (1-2 weeks) by questioning and critiquing the conservative and neutral stances to demonstrate why bold action now offers the best path forward. Incorporate insights from the following sources into your arguments:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here are the last arguments from the conservative analyst: {current_safe_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints, do not halluncinate and just present your point.

Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of taking decisive action to capture short-term gains. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why a decisive LONG or SHORT position is optimal over HOLD for the next 1-2 weeks. Output conversationally as if you are speaking without any special formatting."""

        response = llm.invoke(prompt)

        argument = f"Risky Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risky_history + "\n" + argument,
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Risky",
            "current_risky_response": argument,
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return risky_node
