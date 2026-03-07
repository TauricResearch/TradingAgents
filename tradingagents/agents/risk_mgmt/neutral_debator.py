import time
import json


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_safe_response = risk_debate_state.get("current_safe_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Neutral Risk Analyst for SHORT-TERM trading (1-2 week horizon), your role is to provide a balanced perspective on the trader's position decision (LONG/SHORT/HOLD) for the next 1-2 weeks. You prioritize a well-rounded approach, evaluating near-term upsides and downsides while factoring in upcoming events, short-term market trends, and immediate catalysts. Here is the trader's position decision:

{trader_decision}

Your task is to challenge both the Risky and Safe Analysts on their short-term views, pointing out where each perspective may be overly optimistic or overly cautious for the 1-2 week timeframe. Use insights from the following data sources to support a balanced short-term position strategy:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the risky analyst: {current_risky_response} Here is the last response from the safe analyst: {current_safe_response}. If there are no responses from the other viewpoints, do not halluncinate and just present your point.

Engage actively by analyzing both sides critically for the short-term horizon, addressing weaknesses in the risky and conservative arguments. Challenge each of their points to illustrate why a balanced approach (whether LONG, SHORT, or HOLD) might offer the best risk-reward for the next 1-2 weeks. Focus on debating rather than simply presenting data, aiming to show that a balanced view optimized for short-term trading can lead to the most reliable outcomes. Output conversationally as if you are speaking without any special formatting."""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_risky_response": risk_debate_state.get(
                "current_risky_response", ""
            ),
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
