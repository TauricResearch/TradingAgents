"""Neutral risk debater — adapted for Kalshi prediction-market sizing.

Argues for a **balanced Kelly fraction** that captures edge without
absorbing variance the bankroll can't afford. Mediates between the
Aggressive and Conservative analysts.
"""


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        on_chain_report = state.get("on_chain_report", "")
        contract_id = state.get("company_of_interest", "")

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Neutral Risk Analyst on a Kalshi prediction-market desk, your job is to triangulate between the Aggressive and Conservative views. Champion the Kelly fraction that maximizes long-run bankroll growth given honest probability and confidence inputs — typically a fractional-Kelly multiplier in the 0.20–0.50 range, scaled by confidence band.

Contract under analysis: `{contract_id}`
Trader's transaction proposal:
{trader_decision}

Your stance: critique both aggressive over-sizing and conservative under-sizing using the actual data. Cite specific evidence from the reports below. Recommend a stake fraction that respects (a) the magnitude of the edge, (b) the confidence in the p_yes estimate, (c) the bankroll math (Kelly × confidence-discount). Don't be a fence-sitter — commit to a number with reasoning.

Resources available:
Market technicals report: {market_research_report}
Sentiment report: {sentiment_report}
News report: {news_report}
On-chain report: {on_chain_report}
Conversation so far: {history}
Last aggressive argument: {current_aggressive_response}
Last conservative argument: {current_conservative_response}

If the other analysts haven't spoken yet, present your own opening argument from the data. Output conversationally, no special formatting."""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
