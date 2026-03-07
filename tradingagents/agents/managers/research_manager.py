import time
import json


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""As the portfolio manager and debate facilitator for SHORT-TERM trading (1-2 week horizon), your role is to critically evaluate this round of debate and make a definitive position decision: align with the bull analyst (LONG), the bear analyst (SHORT), or choose HOLD only if it is strongly justified based on the arguments presented.

Focus on SHORT-TERM factors: near-term catalysts, momentum, upcoming events, and what is likely to happen in the next 1-2 weeks. Summarize the key points from both sides concisely, focusing on the most compelling evidence for short-term price movement. Your position recommendation—LONG, SHORT, or HOLD—must be clear and actionable for a 1-2 week holding period. Avoid defaulting to HOLD simply because both sides have valid points; commit to a stance grounded in the debate's strongest short-term arguments.

Additionally, develop a detailed SHORT-TERM investment plan for the trader. This should include:

Your Position Recommendation: A decisive stance (LONG/SHORT/HOLD) for the next 1-2 weeks supported by the most convincing arguments.
Rationale: An explanation of why these arguments lead to your conclusion for the short-term.
Strategic Actions: Concrete steps for implementing the recommendation with a 1-2 week timeframe in mind.
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
