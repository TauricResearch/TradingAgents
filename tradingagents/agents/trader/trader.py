import functools
import time
import json


def create_trader(llm, memory):
    def trader_node(state, name):
        active = state.get("active_hypothesis")
        if active:
            action = (active.get("immediate_action") or active.get("action") or "").lower()
            if action not in {"escalate", "trade", "execute"}:
                return {
                    "trader_investment_plan": state.get("trader_investment_plan", ""),
                    "sender": name,
                }
        company_name = state.get("target_ticker") or state["company_of_interest"]
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        portfolio_summary = state.get("portfolio_summary", "")

        curr_situation = (
            f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        )
        if portfolio_summary:
            curr_situation += f"\n\nPortfolio Briefing:\n{portfolio_summary}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        context_message = (
            f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. "
            "This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. "
            "Use this plan as a foundation for evaluating your next trading decision."
            f"\n\nProposed Investment Plan: {investment_plan}"
        )
        if portfolio_summary:
            context_message += (
                "\n\nCurrent Portfolio Briefing:\n"
                f"{portfolio_summary}\n"
                "Ensure any trade recommendation respects buying power, risk limits, and existing exposures."
            )

        context = {
            "role": "user",
            "content": context_message,
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are a trading agent analyzing market data to make investment decisions. Based on your analysis, provide a specific recommendation to buy, sell, or hold. End with a firm decision and always conclude your response with 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**' to confirm your recommendation. Do not forget to utilize lessons from past decisions to learn from your mistakes. Here is some reflections from similar situatiosn you traded in and the lessons learned: {past_memory_str}""",
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
