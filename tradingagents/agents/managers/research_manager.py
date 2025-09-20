def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        if not state or not isinstance(state, dict):
            raise ValueError("Invalid state provided to research_manager")

        investment_debate_state = state.get("investment_debate_state", {})
        history = investment_debate_state.get("history", "")
        market_research_report = state.get("market_report", "")
        sentiment_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        fundamentals_report = state.get("fundamentals_report", "")

        curr_situation = f"Market: {market_research_report}\nSentiment: {sentiment_report}\nNews: {news_report}\nFundamentals: {fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=3, min_similarity=0.8)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                similarity = rec.get("similarity_score", 0)
                past_memory_str += f"Research Memory {i} (similarity: {similarity:.3f}): {rec['recommendation']}\n\n"
        else:
            past_memory_str = "No statistically significant research memories found (similarity < 80%)."

        prompt = f"""As the portfolio manager and debate facilitator, your role is to critically evaluate this round of debate and make a definitive decision: align with the bear analyst, the bull analyst, or choose Hold only if it is strongly justified based on the arguments presented.

Summarize the key points from both sides concisely, focusing on the most compelling evidence or reasoning. Your recommendation—Buy, Sell, or Hold—must be clear and actionable. Avoid defaulting to Hold simply because both sides have valid points; commit to a stance grounded in the debate's strongest arguments.

Additionally, develop a detailed investment plan for the trader. This should include:

Your Recommendation: A decisive stance supported by the most convincing arguments.
Rationale: An explanation of why these arguments lead to your conclusion.
Strategic Actions: Concrete steps for implementing the recommendation.
Take into account your past mistakes on similar situations. Use these insights to refine your decision-making and ensure you are learning and improving. Present your analysis conversationally, as if speaking naturally, without special formatting. 

Here are your past reflections on mistakes:
\"{past_memory_str}\"

Here is the debate:
Debate History:
{history}"""
        response = llm.invoke(prompt)

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
