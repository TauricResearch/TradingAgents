import time
import json


def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:

        company_name = state["company_of_interest"]

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["news_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""As the Risk Management Judge and Debate Facilitator for SHORT-TERM trading (1-2 week horizon), your goal is to evaluate the debate between three risk analysts—Risky, Neutral, and Safe/Conservative—and determine the best position for the trader over the next 1-2 weeks. Your decision must result in a clear position recommendation: LONG, SHORT, or HOLD. Choose HOLD only if strongly justified by specific arguments, not as a fallback when all sides seem valid. Strive for clarity and decisiveness.

Guidelines for Decision-Making (1-2 week timeframe):
1. **Summarize Key Arguments**: Extract the strongest points from each analyst, focusing on relevance to SHORT-TERM price movement.
2. **Provide Rationale**: Support your recommendation with direct quotes and counterarguments from the debate, emphasizing near-term factors.
3. **Refine the Trader's Plan**: Start with the trader's original plan, **{trader_plan}**, and adjust it based on the analysts' insights for a 1-2 week holding period.
4. **Learn from Past Mistakes**: Use lessons from **{past_memory_str}** to address prior misjudgments and improve the decision you are making now to make sure you don't make a wrong LONG/SHORT/HOLD call that loses money in the short term.

Deliverables:
- A clear and actionable position recommendation: LONG, SHORT, or HOLD for the next 1-2 weeks.
- Detailed reasoning anchored in the debate and past reflections, focusing on short-term factors.

---

**Analysts Debate History:**
{history}

---

Focus on actionable SHORT-TERM insights and continuous improvement. Build on past lessons, critically evaluate all perspectives, and ensure each decision optimizes for the 1-2 week timeframe."""

        response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "risky_history": risk_debate_state["risky_history"],
            "safe_history": risk_debate_state["safe_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_risky_response": risk_debate_state["current_risky_response"],
            "current_safe_response": risk_debate_state["current_safe_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return risk_manager_node
