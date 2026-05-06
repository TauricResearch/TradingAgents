"""Conservative risk debater — adapted for Kalshi prediction-market sizing.

Argues for a **smaller Kelly fraction** (or PASS) when edge confidence
is shaky, the analyst committee was split, or the resolution event
has tail risks the committee may have under-weighted.
"""


def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        on_chain_report = state.get("on_chain_report", "")
        contract_id = state.get("company_of_interest", "")

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Conservative Risk Analyst on a Kalshi prediction-market desk, your priority is bankroll preservation. Each daily contract is a fresh roll of the dice; over-sizing on shaky edge accelerates ruin even when individual calls are right.

Contract under analysis: `{contract_id}`
Trader's transaction proposal:
{trader_decision}

Your stance: argue for a smaller Kelly fraction — or for PASS — when (a) the analyst committee diverged materially, (b) confidence is anything less than high, (c) recent tail-risk signals from on-chain or news could blindside the resolution. Push back on the aggressive analyst's confidence. Specifically critique their reasoning, citing the reports below. Stay grounded in prediction-market math — undersized stakes still grow bankroll over many trades; ruined bankrolls grow nothing.

Resources available:
Market technicals report: {market_research_report}
Sentiment report: {sentiment_report}
News report: {news_report}
On-chain report: {on_chain_report}
Conversation so far: {history}
Last aggressive argument: {current_aggressive_response}
Last neutral argument: {current_neutral_response}

If the other analysts haven't spoken yet, present your own opening argument from the data. Output conversationally, no special formatting."""

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
