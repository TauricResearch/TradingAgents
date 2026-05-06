"""YES-side researcher for Kalshi prediction-market contracts.

Re-framed from the equity-era "Bull" researcher: instead of arguing for
"the stock will go up", this analyst argues that the **YES side of the
Kalshi contract is mispriced cheap** — i.e., the market's implied
probability is below the agent committee's true probability. Symmetric
counterpart: ``bear_researcher`` argues NO is mispriced cheap.
"""


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        on_chain_report = state.get("on_chain_report", "")
        contract_id = state.get("company_of_interest", "")

        prompt = f"""You are the YES-side analyst for a Kalshi prediction-market contract: contract `{contract_id}`. Your job is to build a strong, evidence-based case that the **YES side is mispriced cheap** — i.e., the true probability of YES resolving is meaningfully higher than the Kalshi market currently implies.

Frame your argument as a probability case, not an asset-direction call:
- What is the strongest evidence that the resolution event will occur?
- Where is the market underestimating that probability, and why?
- What signals — technical, news, sentiment, on-chain — converge on YES?
- Where is the NO analyst's case weakest? Engage their argument directly.

Your edge over retail traders is institutional-grade synthesis: cite specific data points from the analyst reports, do not hand-wave. If a contrary signal appears in the data, acknowledge it and explain why it does not invalidate the YES case.

Resources available:
Market technicals report: {market_research_report}
Sentiment report (Reddit + CMC): {sentiment_report}
News report (crypto headlines): {news_report}
On-chain report (chain flows / mempool): {on_chain_report}
Conversation history of the debate: {history}
Last NO-side argument: {current_response}

Deliver a compelling YES-side argument, refute the NO analyst's concerns, and engage in dynamic debate. Output conversationally, no special formatting.
"""

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
