from langchain_core.messages import AIMessage
import time
import json


def create_no_researcher(llm, memory):
    def no_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        no_history = investment_debate_state.get("no_history", "")

        current_response = investment_debate_state.get("current_response", "")
        event_report = state["event_report"]
        odds_report = state["odds_report"]
        information_report = state["information_report"]
        sentiment_report = state["sentiment_report"]

        curr_situation = f"{event_report}\n\n{odds_report}\n\n{information_report}\n\n{sentiment_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""You are a NO Analyst making the case that the prediction market event will NOT occur. Your goal is to present a well-reasoned argument that the YES probability should be lower than the current market price. Leverage the provided research and data to highlight potential obstacles and counter YES arguments effectively.

Key points to focus on:

- Risks and Obstacles: Highlight factors like structural barriers, historical base rates, opposing forces, or conditions that make the event unlikely to occur.
- Market Overpricing: Argue why the current market odds overvalue the YES outcome, identifying where optimism bias or herding behavior may be inflating the price.
- Negative Indicators: Use evidence from event analysis, historical precedent, expert opinions, or recent adverse developments to support your position.
- YES Counterpoints: Critically analyze the YES argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the YES analyst's points and debating effectively rather than simply listing facts.

Resources available:

Event analysis report: {event_report}
Market odds report: {odds_report}
Information and news report: {information_report}
Public sentiment report: {sentiment_report}
Conversation history of the debate: {history}
Last YES argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling NO argument, refute the YES analyst's claims, and engage in a dynamic debate that demonstrates why the event is less likely to occur than the market currently implies. You must also address reflections and learn from lessons and mistakes you made in the past.
"""

        response = llm.invoke(prompt)

        argument = f"NO Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "no_history": no_history + "\n" + argument,
            "yes_history": investment_debate_state.get("yes_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return no_node
