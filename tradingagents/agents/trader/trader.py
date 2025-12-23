# -*- coding: utf-8 -*-
import functools
import time
import json
from tradingagents.agents.utils.prompts import get_trader_prompt


def create_trader(llm, memory, language: str = "zh-TW"):
    """
    建立一個交易員節點。

    Args:
        llm: 用於生成決策的語言模型。
        memory: 儲存過去情況和反思的記憶體物件。
        language: 報告語言 ('en' 或 'zh-TW')

    Returns:
        function: 一個代表交易員節點的函式。
    """

    def trader_node(state, name):
        """交易員節點的執行函式。"""
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
                recommendation = rec["recommendation"]
                past_memory_str += recommendation + "\n\n"
        else:
            past_memory_str = "No past memories found." if language == "en" else "找不到過去的記憶。"

        # Get language-specific prompt
        base_prompt = get_trader_prompt(language)
        
        if language == "en":
            prompt = f"""{base_prompt}

【Available Information】
- Investment Plan: {investment_plan}
- Past Reflections: {past_memory_str}

**IMPORTANT**: End your response with "Final Trading Proposal: **Buy/Hold/Sell**"!"""
            
            system_msg = f"""You are a trading agent analyzing market data to make investment decisions. Based on your analysis, provide specific Buy, Sell, or Hold recommendations. End with a firm decision by always ending your response with "Final Trading Proposal: **Buy/Hold/Sell**" to confirm your recommendation. Don't forget to leverage lessons from past decisions to learn from mistakes. Here are some reflections from similar situations: {past_memory_str}"""
        else:
            prompt = f"""{base_prompt}

【可用資訊】
- 投資計畫：{investment_plan}
- 過去反思：{past_memory_str}

**重要**：請以「最終交易提案：**買入/持有/賣出**」結束回應！"""
            
            system_msg = f"""您是一位分析市場數據以做出投資決策的交易代理。根據您的分析，提供具體的買入、賣出或持有建議。以堅定的決策結束，並始終以「最終交易提案：**買入/持有/賣出**」來結束您的回應，以確認您的建議。不要忘記利用過去決策的教訓來從錯誤中學習。以下是您在類似情況下交易的一些反思：{past_memory_str}"""

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ]

        result = llm.invoke(messages)

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")