from langchain_core.messages import AIMessage
import time
import json
from tradingagents.agents.utils.korean_prompt import (
    KOREAN_INVESTOR_GUIDE,
    KOREAN_DEBATE_GUIDE,
)


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""You are a Bull Analyst evaluating whether to ENTER a NEW long position in this stock. There is currently NO existing position — the question is purely: "Should we buy this stock now as a fresh entry?"

Your task is to build a strong, evidence-based case for entering this new position, emphasizing why NOW is a good entry point based on growth potential, competitive advantages, and positive market indicators.

Key points to focus on:
- Entry Timing: Argue why the current price and market conditions represent a good entry point for a new long position.
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability that justify buying now.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence for entering now.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why entering a new position is still justified.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling argument for entering a new long position, refute the bear's concerns, and engage in a dynamic debate. You must also address reflections and learn from lessons and mistakes you made in the past.
{KOREAN_INVESTOR_GUIDE}
{KOREAN_DEBATE_GUIDE}
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
