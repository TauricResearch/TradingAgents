import functools
import time
import json


def create_trader(llm, memory):
    def trader_node(state, name):
        ticker = state["ticker_of_interest"]
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        base_asset = ""
        quote_asset = ""
        if isinstance(ticker, str) and "/" in ticker:
            base_asset, quote_asset = ticker.split("/", 1)

        pair_context = ticker
        if base_asset and quote_asset:
            pair_context = f"{ticker} (base={base_asset}, quote={quote_asset})"

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is an investment plan for the crypto pair {pair_context}. This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next crypto trading decision.\n\nProposed Investment Plan: {investment_plan}\n\nLeverage these insights to make an informed and strategic decision for this crypto market.",
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are a crypto trading agent analyzing cryptocurrency market data for a specific trading pair (e.g., BTC/USDT). Based on your analysis, provide a specific recommendation to BUY, SELL, or HOLD the base asset relative to the quote asset for the pair {pair_context}. End with a firm decision and always conclude your response with 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**' to confirm your recommendation. Do not forget to utilize lessons from past decisions to learn from your mistakes. Here is some reflections from similar situations you traded in and the lessons learned: {past_memory_str}""",
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
