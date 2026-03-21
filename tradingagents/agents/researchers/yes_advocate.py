

def create_yes_advocate(llm, memory):
    def yes_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        yes_history = investment_debate_state.get("yes_history", "")
        event_question = state["event_question"]

        current_no_response = investment_debate_state.get("current_no_response", "")
        current_timing_response = investment_debate_state.get("current_timing_response", "")

        odds_report = state["odds_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        event_report = state["event_report"]

        curr_situation = f"{odds_report}\n\n{sentiment_report}\n\n{news_report}\n\n{event_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)
        past_memory_str = ""
        for rec in past_memories:
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""You are the YES Advocate for the prediction market question: "{event_question}"

Your task is to build a strong, evidence-based case that this event WILL occur (YES outcome). Leverage the provided research and data to support your position and counter opposing arguments.

Key points to focus on:
- Evidence Supporting YES: Highlight data, news, and trends that increase the probability of YES.
- Counterarguments: Directly address and rebut the NO Advocate's concerns and the Timing Advocate's hesitations.
- Market Mispricing: If the current odds undervalue YES, explain why using specific evidence.
- Engagement: Present your argument conversationally, engaging directly with opposing points rather than just listing facts.

Resources:
Odds & Market Analysis: {odds_report}
Social Sentiment: {sentiment_report}
News Analysis: {news_report}
Event Analysis: {event_report}
Debate History: {history}
Last NO argument: {current_no_response}
Last Timing argument: {current_timing_response}
Lessons from past predictions: {past_memory_str}

Build a compelling YES case. Address past mistakes and learn from them."""

        response = llm.invoke(prompt)
        argument = f"YES Advocate: {response.content}"

        new_state = {
            "history": history + "\n" + argument,
            "yes_history": yes_history + "\n" + argument,
            "no_history": investment_debate_state.get("no_history", ""),
            "timing_history": investment_debate_state.get("timing_history", ""),
            "current_yes_response": argument,
            "current_no_response": investment_debate_state.get("current_no_response", ""),
            "current_timing_response": investment_debate_state.get("current_timing_response", ""),
            "latest_speaker": "YES Advocate",
            "judge_decision": investment_debate_state.get("judge_decision", ""),
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_state}

    return yes_node
