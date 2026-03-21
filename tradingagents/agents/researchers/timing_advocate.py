

def create_timing_advocate(llm, memory):
    def timing_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        timing_history = investment_debate_state.get("timing_history", "")
        event_question = state["event_question"]

        current_yes_response = investment_debate_state.get("current_yes_response", "")
        current_no_response = investment_debate_state.get("current_no_response", "")

        odds_report = state["odds_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        event_report = state["event_report"]

        curr_situation = f"{odds_report}\n\n{sentiment_report}\n\n{news_report}\n\n{event_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)
        past_memory_str = ""
        for rec in past_memories:
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""You are the Timing Advocate for the prediction market question: "{event_question}"

Your role is distinct from the YES and NO advocates. Even if the outcome might lean YES or NO, your job is to analyze whether the CURRENT market price accurately reflects the true probability and whether there is actionable edge RIGHT NOW.

Key points to focus on:
- Edge vs. Current Odds: Is there actually a mispricing? Compare the implied probability from current odds against your estimated true probability. Only recommend action if there is a meaningful edge.
- Time Decay and Deadline Proximity: How much time remains until resolution? Does the time horizon justify entering a position now, or is there opportunity cost from tying up capital?
- Market Efficiency: Has the market already priced in the likely outcome based on recent news and events? If so, the opportunity may have passed.
- Liquidity Traps: Can you actually execute at current prices, or is the market thin and spread too wide to make entry worthwhile?
- Wait for Better Odds: Would waiting for a market overreaction — a temporary price swing — yield a better entry point with higher expected value?
- SKIP Recommendation: If the current market offers no meaningful edge, recommend SKIP and explain why patience is the right strategy here.

Resources:
Odds & Market Analysis: {odds_report}
Social Sentiment: {sentiment_report}
News Analysis: {news_report}
Event Analysis: {event_report}
Debate History: {history}
Last YES argument: {current_yes_response}
Last NO argument: {current_no_response}
Lessons from past predictions: {past_memory_str}

Provide a rigorous timing and value analysis. Address past mistakes and learn from them."""

        response = llm.invoke(prompt)
        argument = f"Timing Advocate: {response.content}"

        new_state = {
            "history": history + "\n" + argument,
            "yes_history": investment_debate_state.get("yes_history", ""),
            "no_history": investment_debate_state.get("no_history", ""),
            "timing_history": timing_history + "\n" + argument,
            "current_yes_response": investment_debate_state.get("current_yes_response", ""),
            "current_no_response": investment_debate_state.get("current_no_response", ""),
            "current_timing_response": argument,
            "latest_speaker": "Timing Advocate",
            "judge_decision": investment_debate_state.get("judge_decision", ""),
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_state}

    return timing_node
