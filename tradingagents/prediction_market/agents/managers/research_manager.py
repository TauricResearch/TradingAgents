import time
import json


def create_pm_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        history = state["investment_debate_state"].get("history", "")
        event_report = state["event_report"]
        odds_report = state["odds_report"]
        information_report = state["information_report"]
        sentiment_report = state["sentiment_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{event_report}\n\n{odds_report}\n\n{information_report}\n\n{sentiment_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""As the research manager and debate judge for this prediction market analysis, your role is to critically evaluate the YES/NO debate and produce a definitive investment thesis. You must commit to a clear directional view rather than defaulting to neutrality.

Synthesize the key arguments from both the YES and NO analysts, focusing on the most compelling evidence. Your output must include:

1. Estimated True Probability: Your best estimate of the actual probability the event occurs, expressed as a percentage.
2. Market Price Comparison: How your estimated probability compares to the current market-implied odds.
3. Edge Calculation: The difference between your estimated probability and the market price. Positive edge means YES is underpriced; negative edge means YES is overpriced.
4. Confidence Level: How confident you are in your probability estimate (low, medium, or high), with justification.
5. Recommendation: A decisive stance — BUY YES, BUY NO, or HOLD — supported by the strongest arguments from the debate.
6. Rationale: An explanation of why these arguments lead to your conclusion.
7. Strategic Actions: Concrete steps for implementing the recommendation, including position sizing guidance based on edge size and confidence.

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
            "no_history": investment_debate_state.get("no_history", ""),
            "yes_history": investment_debate_state.get("yes_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
