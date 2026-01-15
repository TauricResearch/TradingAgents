import functools
import time
import json


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
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

        market_regime = state.get("market_regime", "UNKNOWN")
        volatility_score = state.get("volatility_score", "UNKNOWN")

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {investment_plan}\nMARKET REGIME SIGNAL: {market_regime}\nVOLATILE METRICS: {volatility_score}\n\nLeverage these insights to make an informed and strategic decision.",
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are the Portfolio Manager. You have final authority.
Your goal is Alpha generation with SURVIVAL priority.

CURRENT MARKET REGIME: {market_regime} (Read this carefully!)


CRITICAL MENTAL MODELS FOR TECH/PLATFORM ANALYSIS:
1. CAPEX DISTINCTION: Distinguish between "Maintenance CapEx" (Cost) and "Strategic CapEx" (Moat Building). 
   - For dominant platforms (Google, Amazon, MSFT), massive CapEx during platform shifts (e.g., AI) is a BULLISH signal of defense, not a bearish signal of inefficiency.
   
2. REGULATORY OVERHANG: Treat antitrust risk as a "Chronic Condition" (reduce position size slightly) rather than a "Terminal Disease" (sell everything), unless an explicit breakup order is imminent.

3. VALUATION: Do not benchmark Platform Monopolies against the S&P 500 P/E. Benchmark them against their durability, net cash position, and pricing power.

DECISION LOGIC:
1. IF Regime == 'VOLATILE' OR 'TRENDING_DOWN':
   - You are in "FALLING KNIFE" mode.
   - Ignore Bullish "Growth" arguments unless they are overwhelming.
   - High probability action: HOLD or SELL.
   - Only BUY if: RSI < 30 AND Regime is reversing.

2. IF Regime == 'TRENDING_UP':
   - You are in "MOMENTUM" mode.
   - Prioritize Bullish signals.
   - Buy dips.

3. IF Regime == 'SIDEWAYS':
   - Buy Support, Sell Resistance.

FINAL OUTPUT:
End with 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**'. Do not forget to utilize lessons from past decisions to learn from your mistakes. Here is some reflections from similar situatiosn you traded in and the lessons learned: {past_memory_str}""",
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
