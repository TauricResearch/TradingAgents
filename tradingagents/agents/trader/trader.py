import functools


def create_trader(llm, memory):
    def trader_node(state, name):
        event_id = state["event_id"]
        event_question = state["event_question"]
        investment_plan = state["investment_plan"]
        odds_report = state["odds_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        event_report = state["event_report"]

        curr_situation = f"{odds_report}\n\n{sentiment_report}\n\n{news_report}\n\n{event_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for rec in past_memories:
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is a prediction plan for the event: '{event_question}' (Event ID: {event_id}). This plan incorporates insights from market odds, news, social sentiment, and event analysis. Use this plan to formulate your betting decision.\n\nProposed Plan: {investment_plan}\n\nLeverage these insights to make an informed and strategic prediction.",
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are a prediction market trader analyzing event data to make betting decisions on Polymarket. Based on your analysis, provide a specific recommendation: YES (bet on event occurring), NO (bet against event occurring), or SKIP (no bet).

Consider the edge (difference between your estimated probability and market price), position sizing, and risk management. End with a firm decision and always conclude your response with 'FINAL PREDICTION: **YES/NO/SKIP** | Confidence: X.X | Edge: X.X' to confirm your recommendation.

Utilize lessons from past decisions to learn from mistakes: {past_memory_str}""",
            },
            context,
        ]

        result = llm.invoke(messages)

        return {
            "messages": [result],
            "trader_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
