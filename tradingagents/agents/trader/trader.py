import functools
import time
import json
from tradingagents.dataflows.config import get_config


def get_trader_system_message(language="en", past_memory_str=""):
    """Get trader system message in the specified language."""
    if language == "zh_TW":
        return f"""你是一位交易代理人，分析市場數據以做出投資決策。根據你的分析，提供買入、賣出或持有的具體建議。以明確的決定結束，並始終以 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**' 結論你的回應，以確認你的建議。不要忘記從過去的決定中學習教訓。以下是你過去交易過的類似情況的一些反思和學到的經驗：{past_memory_str}"""
    else:
        return f"""You are a trading agent analyzing market data to make investment decisions. Based on your analysis, provide a specific recommendation to buy, sell, or hold. End with a firm decision and always conclude your response with 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**' to confirm your recommendation. Do not forget to utilize lessons from past decisions to learn from your mistakes. Here is some reflections from similar situatiosn you traded in and the lessons learned: {past_memory_str}"""


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

        # Get language from config, default to English
        config = get_config()
        language = config.get("language", "en")

        # Get user context based on language
        if language == "zh_TW":
            user_content = f"基於一個分析師團隊的全面分析，這是為 {company_name} 量身定制的投資計劃。該計劃融入了當前技術市場趨勢、宏觀經濟指標和社交媒體情感的見解。使用此計劃作為評估你下一個交易決定的基礎。\n\n建議的投資計劃：{investment_plan}\n\n利用這些見解來做出知情和戰略性的決定。"
        else:
            user_content = f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {investment_plan}\n\nLeverage these insights to make an informed and strategic decision."

        context = {
            "role": "user",
            "content": user_content,
        }

        messages = [
            {
                "role": "system",
                "content": get_trader_system_message(language, past_memory_str),
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
