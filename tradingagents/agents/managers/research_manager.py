

def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        history = state["investment_debate_state"].get("history", "")
        odds_report = state["odds_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        event_report = state["event_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{odds_report}\n\n{sentiment_report}\n\n{news_report}\n\n{event_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""As the research manager and debate judge, your role is to critically evaluate this 3-way debate between the YES Advocate, NO Advocate, and Timing Advocate, and make a definitive decision: YES, NO, or SKIP.

Summarize the key points from all three sides concisely, focusing on the most compelling evidence or reasoning. Your recommendation must be clear and actionable:
- YES: Bet that the event will occur (buy YES shares).
- NO: Bet that the event will not occur (buy NO shares).
- SKIP: There is no meaningful edge at current prices — pass on this market entirely.

Avoid defaulting to SKIP simply because all sides have valid points; commit to a stance grounded in the debate's strongest arguments and the actual market edge.

Additionally, develop a detailed investment plan for the trader. This should include:

Your Recommendation: A decisive stance (YES / NO / SKIP) supported by the most convincing arguments.
Confidence Level: High / Medium / Low — reflecting your certainty in the recommendation.
Estimated True Probability: Your best estimate of the actual probability of the YES outcome (e.g., "We estimate ~65% true probability vs. 50% implied by current odds").
Rationale: An explanation of why these arguments lead to your conclusion.
Strategic Actions: Concrete steps for implementing the recommendation (entry price targets, position sizing, exit conditions).

Take into account past mistakes on similar situations. Use these insights to refine your decision-making and ensure you are learning and improving. Present your analysis conversationally, as if speaking naturally, without special formatting.

Here are your past reflections on mistakes:
\"{past_memory_str}\"

Here is the debate:
Debate History:
{history}"""

        response = llm.invoke(prompt)

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "yes_history": investment_debate_state.get("yes_history", ""),
            "no_history": investment_debate_state.get("no_history", ""),
            "timing_history": investment_debate_state.get("timing_history", ""),
            "current_yes_response": investment_debate_state.get("current_yes_response", ""),
            "current_no_response": investment_debate_state.get("current_no_response", ""),
            "current_timing_response": investment_debate_state.get("current_timing_response", ""),
            "latest_speaker": "Research Manager",
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
