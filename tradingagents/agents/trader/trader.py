import functools

from tradingagents.agents.utils.agent_utils import (
    build_capital_context,
    build_instrument_context,
    get_language_instruction,
)


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        capital_context = build_capital_context(state.get("holdings_info"))
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        holdings_info = state.get("holdings_info") or {}
        if holdings_info:
            quantity = holdings_info.get("quantity")
            avg_buy_price = holdings_info.get("avg_buy_price")
            holdings_str = f"Quantity: {quantity}, Average buy price: {avg_buy_price}"
        else:
            holdings_str = "No current holdings."

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        memory_section = (
            f" Here are reflections from similar situations you traded in and the lessons learned: {past_memory_str}"
            if past_memory_str else ""
        )

        capital_block = f"\n\n{capital_context}" if capital_context else ""
        context = {
            "role": "user",
            "content": f"Investment plan for {company_name}. {instrument_context}{capital_block}\n\nProposed Investment Plan: {investment_plan}",
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are a short-term trader. Based on the investment plan, provide a trade recommendation that includes all of the following parameters:
- **Action**: BUY / HOLD / SELL
- **Entry price range**: specific price level or range to enter the trade
- **Stop loss**: exact price level to exit and limit losses
- **Take profit target**: exact price level to take profits
- **Holding period**: expected hold duration in days or weeks
- **Holdings management**: current position is {holdings_str} — give explicit instructions on how to manage it
Always conclude with 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**'.{memory_section}{get_language_instruction()}""",
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
