"""Risk Reviewer: single LLM-based reviewer that replaces the 3-way risk debate.

Variation 2 of the experiment. The 3-personality risk debate (Aggressive /
Conservative / Neutral) tends to produce stylised disagreement rather than
new information. This single reviewer is asked to identify the *actual*
risks to the trader's proposal and call out anything that should change
the size or direction of the position.
"""

from __future__ import annotations


def create_risk_reviewer(llm):
    def risk_reviewer_node(state) -> dict:
        trader_decision = state["trader_investment_plan"]
        market = state["market_report"]
        sentiment = state["sentiment_report"]
        news = state["news_report"]
        fundamentals = state["fundamentals_report"]

        prompt = f"""You are a Risk Reviewer. Your job is to stress-test the trader's proposal — not by adopting a personality, but by identifying the actual ways this trade could go wrong and saying whether the size and direction are appropriate given those risks.

Trader's proposal:
{trader_decision}

Cover, in this order:
1. **Material risks**: The two or three risks that genuinely matter for this trade over the next 1–3 months. Skip generic risks (rates, recession) unless they're acute right now.
2. **Position sizing check**: Given those risks, is the proposed size reasonable, too large, or too small?
3. **Recommendation to the PM**: Concrete guidance — proceed as proposed, modify (and how), or reject.

Resources:
- Market research: {market}
- Sentiment: {sentiment}
- News: {news}
- Fundamentals: {fundamentals}

Be specific, cite evidence, and avoid bothsidesing."""

        response = llm.invoke(prompt)
        argument = f"Risk Reviewer:\n{response.content}"

        risk_debate_state = state["risk_debate_state"]
        new_state = {
            "history": argument,
            "aggressive_history": argument,
            "conservative_history": argument,
            "neutral_history": argument,
            "latest_speaker": "RiskReviewer",
            "current_aggressive_response": argument,
            "current_conservative_response": argument,
            "current_neutral_response": argument,
            "judge_decision": risk_debate_state.get("judge_decision", ""),
            "count": risk_debate_state.get("count", 0) + 1,
        }
        return {"risk_debate_state": new_state}

    return risk_reviewer_node
