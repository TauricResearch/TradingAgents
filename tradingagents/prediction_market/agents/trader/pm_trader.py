import functools


def create_pm_trader(llm, memory):
    def trader_node(state, name):
        market_question = state["market_question"]
        investment_plan = state["investment_plan"]
        event_report = state["event_report"]
        odds_report = state["odds_report"]
        information_report = state["information_report"]
        sentiment_report = state["sentiment_report"]

        curr_situation = f"{event_report}\n\n{odds_report}\n\n{information_report}\n\n{sentiment_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        context = {
            "role": "user",
            "content": (
                f"You are evaluating a prediction market position for the following question:\n\n"
                f"MARKET QUESTION: {market_question}\n\n"
                f"Based on a comprehensive analysis by a team of analysts, here is the investment plan "
                f"synthesized from event analysis, odds analysis, information research, and sentiment analysis. "
                f"Use this plan as a foundation for your trading decision.\n\n"
                f"Proposed Investment Plan:\n{investment_plan}\n\n"
                f"Event Analysis Report:\n{event_report}\n\n"
                f"Odds Analysis Report:\n{odds_report}\n\n"
                f"Information Analysis Report:\n{information_report}\n\n"
                f"Sentiment Analysis Report:\n{sentiment_report}\n\n"
                f"Leverage these insights to make an informed and strategic trading decision."
            ),
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are a prediction market trader analyzing market data to make trading decisions on binary outcome markets. Your goal is to identify mispriced contracts and exploit the edge between your estimated true probability and the current market price.

DECISION FRAMEWORK:
1. Estimate the TRUE PROBABILITY of the event occurring based on all available analysis.
2. Compare your estimated probability against the current market price (from the odds report).
3. Calculate your EDGE: Edge = |Estimated Probability - Market Price|
4. Apply a MINIMUM EDGE THRESHOLD of 5%. If your edge is below 5%, you MUST recommend PASS regardless of direction.
5. For position sizing, use 0.25x FRACTIONAL KELLY CRITERION:
   - Kelly fraction = edge / odds_against
   - Position size = 0.25 * Kelly fraction * bankroll
   - This conservative sizing protects against estimation errors.

YOUR ANALYSIS MUST INCLUDE:
- Your estimated true probability (with reasoning)
- The current market price
- Your calculated edge (estimated probability minus market price)
- Whether the edge exceeds the 5% minimum threshold
- Position sizing reasoning using fractional Kelly
- Key risks that could invalidate your probability estimate

DECISION OPTIONS:
- BUY_YES: You believe the event is MORE likely than the market implies (your probability > market price + 5%)
- BUY_NO: You believe the event is LESS likely than the market implies (your probability < market price - 5%)
- PASS: Your edge is below 5%, or uncertainty is too high to have conviction

Do not forget to utilize lessons from past decisions to learn from your mistakes. Here are reflections from similar situations you traded in and the lessons learned:
{past_memory_str}

Always conclude your response with 'FINAL TRADE PROPOSAL: **BUY_YES/BUY_NO/PASS**' to confirm your recommendation.""",
            },
            context,
        ]

        result = llm.invoke(messages)

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
