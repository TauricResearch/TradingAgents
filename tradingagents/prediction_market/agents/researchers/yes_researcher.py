from langchain_core.messages import AIMessage
import time
import json


def create_yes_researcher(llm, memory):
    def yes_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        yes_history = investment_debate_state.get("yes_history", "")

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

        prompt = f"""You are a YES Analyst advocating that the prediction market event WILL occur. Your task is to build a strong, evidence-based case that the YES probability should be higher than the current market price. Leverage the provided research and data to address concerns and counter NO arguments effectively.

Key points to focus on:
- Supporting Evidence: Highlight concrete indicators, trends, and data points that suggest the event is likely to occur.
- Probability Assessment: Argue why the current market odds undervalue the YES outcome, identifying where the market may be mispricing risk.
- Positive Catalysts: Emphasize upcoming events, momentum shifts, or developments that increase the likelihood of the event occurring.
- NO Counterpoints: Critically analyze the NO argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the YES perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the NO analyst's points and debating effectively rather than just listing data.

Resources available:
Event analysis report: {event_report}
Market odds report: {odds_report}
Information and news report: {information_report}
Public sentiment report: {sentiment_report}
Conversation history of the debate: {history}
Last NO argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling YES argument, refute the NO analyst's concerns, and engage in a dynamic debate that demonstrates why the event is more likely to occur than the market currently implies. You must also address reflections and learn from lessons and mistakes you made in the past.
"""

        response = llm.invoke(prompt)

        argument = f"YES Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "yes_history": yes_history + "\n" + argument,
            "no_history": investment_debate_state.get("no_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return yes_node
