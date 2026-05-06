"""NO-side researcher for Kalshi prediction-market contracts.

Re-framed from the equity-era "Bear" researcher: argues that the **NO
side of the Kalshi contract is mispriced cheap** — i.e., the true
probability of YES resolving is meaningfully *lower* than the market
currently implies, so taking NO at the implied price has positive
expected value.
"""


def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        on_chain_report = state.get("on_chain_report", "")
        contract_id = state.get("company_of_interest", "")

        prompt = f"""You are the NO-side analyst for a Kalshi prediction-market contract: contract `{contract_id}`. Your job is to build a strong, evidence-based case that the **NO side is mispriced cheap** — i.e., the true probability of YES resolving is meaningfully *lower* than the Kalshi market currently implies, so taking NO at the implied price has positive expected value.

Frame your argument as a probability case, not a market-doom call:
- What is the strongest evidence the resolution event will not occur?
- Where is the market overestimating YES probability, and why?
- What signals — technical, news, sentiment, on-chain — converge on NO?
- Where is the YES analyst's case weakest? Engage their argument directly.

Your edge over retail traders is institutional-grade synthesis: cite specific data points from the analyst reports, do not hand-wave. If a contrary signal appears in the data, acknowledge it and explain why it does not invalidate the NO case.

Resources available:
Market technicals report: {market_research_report}
Sentiment report (Reddit + CMC): {sentiment_report}
News report (crypto headlines): {news_report}
On-chain report (chain flows / mempool): {on_chain_report}
Conversation history of the debate: {history}
Last YES-side argument: {current_response}

Deliver a compelling NO-side argument, refute the YES analyst's claims, and engage in dynamic debate. Output conversationally, no special formatting.
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
