from langchain_core.messages import AIMessage
import time
import json
from tradingagents.agents.utils.korean_prompt import (
    KOREAN_INVESTOR_GUIDE,
    KOREAN_DEBATE_GUIDE,
)


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

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

        prompt = f"""You are a Bear Analyst making the case AGAINST entering a NEW long position in this stock. There is currently NO existing position — the question is purely: "Should we buy this stock now as a fresh entry?" Your goal is to argue NO — that entering a new position now is too risky or ill-timed.

Present a well-reasoned argument emphasizing why this is a bad entry point, highlighting risks, challenges, and negative indicators that make buying now inadvisable.

Key points to focus on:

- Poor Entry Timing: Argue why the current price, valuation, or market conditions make this a bad moment to initiate a new long position.
- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could cause losses after entry.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support passing on this trade.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions about entry timing.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling argument for passing on this trade, refute the bull's claims, and engage in a dynamic debate. You must also address reflections and learn from lessons and mistakes you made in the past.
{KOREAN_INVESTOR_GUIDE}
{KOREAN_DEBATE_GUIDE}
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
