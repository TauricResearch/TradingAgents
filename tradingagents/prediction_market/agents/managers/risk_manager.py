def create_pm_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:
        market_question = state["market_question"]

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        event_report = state["event_report"]
        odds_report = state["odds_report"]
        information_report = state["information_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["trader_investment_plan"]

        curr_situation = f"{event_report}\n\n{odds_report}\n\n{information_report}\n\n{sentiment_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        prompt = f"""As the Risk Management Judge for prediction markets, your goal is to evaluate the debate between three risk analysts -- Aggressive, Neutral, and Conservative -- and determine the best course of action for the trader's proposed position on:

MARKET QUESTION: {market_question}

Your decision must result in a clear recommendation: APPROVE the trade as proposed, MODIFY the trade with specific adjustments, or REJECT the trade entirely. Choose PASS only if strongly justified by specific risk arguments, not as a fallback when all sides seem valid. Strive for clarity and decisiveness.

MANDATORY RISK ASSESSMENTS -- You must explicitly address each of the following:

1. **RESOLUTION RISK**: How clear are the resolution criteria? What is the probability of disputed or ambiguous resolution? Could the market resolve on a technicality that differs from the spirit of the question?

2. **LIQUIDITY RISK**: Can the position be exited if the thesis changes? What is the expected slippage? Is the position size appropriate relative to market depth?

3. **CORRELATION RISK**: Does this position create concentrated exposure to a single event type, domain, or correlated outcome? How would correlated losses across similar positions compound?

Guidelines for Decision-Making:
1. **Summarize Key Arguments**: Extract the strongest points from each analyst, focusing on relevance to the prediction market context.
2. **Provide Rationale**: Support your recommendation with direct quotes and counterarguments from the debate.
3. **Refine the Trader's Plan**: Start with the trader's original plan and adjust it based on the analysts' insights. If the edge is insufficient or the risks too high, recommend PASS.
4. **Learn from Past Mistakes**: Use lessons from past reflections to address prior misjudgments and improve the decision you are making now: {past_memory_str}

Deliverables:
- Explicit assessment of resolution risk, liquidity risk, and correlation risk.
- A clear and actionable recommendation: APPROVE (with the proposed sizing), MODIFY (with specific adjustments to size, direction, or conditions), or REJECT (with reasoning).
- If APPROVE or MODIFY, state the final position: BUY_YES or BUY_NO with sizing guidance.
- If REJECT, the final position is PASS.
- Detailed reasoning anchored in the debate and past reflections.

---

**Trader's Proposed Plan:**
{trader_plan}

**Analysts Debate History:**
{history}

---

Focus on actionable insights and continuous improvement. Build on past lessons, critically evaluate all perspectives, and ensure each decision advances better outcomes.

Always conclude your response with 'FINAL TRADE DECISION: **BUY_YES/BUY_NO/PASS**' to confirm your recommendation."""

        response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return risk_manager_node
