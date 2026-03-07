from langchain_core.messages import AIMessage
import time
import json


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

        prompt = f"""You are a Bull Analyst advocating for taking a LONG position on the stock for SHORT-TERM trading (1-2 week horizon). Your task is to build a strong, evidence-based case emphasizing near-term catalysts, momentum indicators, and positive short-term signals. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on for the next 1-2 weeks:
- Near-Term Catalysts: Highlight upcoming events, earnings, product launches, or announcements that could drive the price up in the next 1-2 weeks.
- Short-Term Momentum: Emphasize positive technical signals, momentum indicators, and recent price action supporting a LONG position.
- Positive Short-Term Indicators: Use recent news, sentiment shifts, and market trends as evidence for going LONG in the near term.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns and showing why the LONG position holds stronger merit over SHORT for the next 1-2 weeks.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bull argument for a SHORT-TERM LONG position (1-2 weeks), refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the LONG position for the near term. You must also address reflections and learn from lessons and mistakes you made in the past.
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
