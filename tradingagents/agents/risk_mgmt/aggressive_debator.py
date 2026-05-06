"""Aggressive risk debater — adapted to Kalshi prediction-market sizing.

Re-framed from the equity-era version: instead of arguing for high-risk
high-reward asset allocation, this analyst pushes for **a larger Kelly
fraction** when the agent committee has identified meaningful edge.
"""


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        on_chain_report = state.get("on_chain_report", "")
        contract_id = state.get("company_of_interest", "")

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Aggressive Risk Analyst on a Kalshi prediction-market desk, you champion sizing UP when the agent committee has identified real edge against the venue. The Trader has proposed a side and stake; your job is to push for a larger Kelly fraction when the data warrants it, and to challenge cautious thinking that leaves alpha on the table.

Contract under analysis: `{contract_id}`
Trader's transaction proposal:
{trader_decision}

Your stance: when multiple analyst reports converge (technicals + on-chain + sentiment + news), the conservative analyst's instinct to stake small is often a tax on conviction. Defend a larger stake. Cite specific points from the reports below to support sizing up. Engage directly with the conservative and neutral analysts, refuting their points one by one. Stay grounded in the prediction-market math — Kelly fraction × edge × bankroll — not generic risk-on rhetoric.

Resources available:
Market technicals report: {market_research_report}
Sentiment report: {sentiment_report}
News report: {news_report}
On-chain report: {on_chain_report}
Conversation so far: {history}
Last conservative argument: {current_conservative_response}
Last neutral argument: {current_neutral_response}

If the other analysts haven't spoken yet, present your own opening argument from the data. Output conversationally, no special formatting."""

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
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
