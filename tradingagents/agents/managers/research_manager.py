import time
import json
from tradingagents.agents.utils.korean_prompt import (
    KOREAN_INVESTOR_GUIDE,
    KOREAN_DEBATE_GUIDE,
)


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

        prompt = f"""As the portfolio manager and debate facilitator, your role is to critically evaluate this round of debate and make a definitive decision on whether to ENTER a NEW long position in this stock.

Context: There is currently NO existing position in this stock. The only question is: "Should we BUY to open a new position now, or PASS and not enter?"

Your decision options are:
- **BUY**: Enter a new long position now — the bull case is compelling and the entry timing is right.
- **PASS**: Do not enter — the risks or poor timing outweigh the opportunity; wait for a better setup.

Summarize the key points from both sides concisely, focusing on the most compelling evidence or reasoning about entry timing and risk/reward. Avoid defaulting to PASS simply because both sides have valid points; commit to a stance grounded in the debate's strongest arguments.

Additionally, develop a detailed entry plan for the trader if recommending BUY. This should include:

Your Recommendation: A decisive BUY or PASS stance supported by the most convincing arguments.
Rationale: An explanation of why these arguments lead to your conclusion about entering now.
Strategic Actions: If BUY — concrete entry parameters (price levels, position sizing approach, stop-loss levels). If PASS — what conditions would need to change before reconsidering entry.
Take into account your past mistakes on similar situations. Use these insights to refine your decision-making and ensure you are learning and improving. Present your analysis conversationally, as if speaking naturally, without special formatting.

Here are your past reflections on mistakes:
\"{past_memory_str}\"

Here is the debate:
Debate History:
{history}

{KOREAN_INVESTOR_GUIDE}
{KOREAN_DEBATE_GUIDE}
"""
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
