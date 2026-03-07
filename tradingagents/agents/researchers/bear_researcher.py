from langchain_core.messages import AIMessage
import time
import json


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

        prompt = f"""You are a Bear Analyst making the case for taking a SHORT position on the stock for SHORT-TERM trading (1-2 week horizon). Your goal is to present a well-reasoned argument emphasizing near-term risks, negative catalysts, and bearish short-term signals. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on for the next 1-2 weeks:

- Near-Term Risks: Highlight upcoming events, earnings risks, negative catalysts, or announcements that could drive the price down in the next 1-2 weeks.
- Short-Term Weakness: Emphasize negative technical signals, overbought conditions, and recent price action supporting a SHORT position.
- Negative Short-Term Indicators: Use recent adverse news, sentiment deterioration, and market headwinds to support the SHORT position in the near term.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions that make LONG risky for the next 1-2 weeks.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bear argument for a SHORT-TERM SHORT position (1-2 weeks), refute the bull's claims, and engage in a dynamic debate that demonstrates why SHORT is preferable over LONG for the near term. You must also address reflections and learn from lessons and mistakes you made in the past.
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
