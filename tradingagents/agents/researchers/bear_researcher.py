# -*- coding: utf-8 -*-
from langchain_core.messages import AIMessage
import time
import json
from tradingagents.agents.utils.output_filter import fix_common_llm_errors, validate_and_warn
from tradingagents.agents.utils.prompts import get_bear_researcher_prompt


def create_bear_researcher(llm, memory, language: str = "zh-TW"):
    """
    建立一個看跌研究員節點。

    Args:
        llm: 用於生成回應的語言模型。
        memory: 儲存過去情況和反思的記憶體物件。
        language: 報告語言 ('en' 或 'zh-TW')

    Returns:
        function: 一個代表看跌研究員節點的函式。
    """

    def bear_node(state) -> dict:
        """看跌研究員節點的執行函式。"""
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")
        current_response = investment_debate_state.get("current_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        
        past_memories = memory.get_memories(curr_situation, n_matches=2)
        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            recommendation = rec["recommendation"]
            past_memory_str += recommendation + "\n\n"

        # Get language-specific prompt template
        base_prompt = get_bear_researcher_prompt(language)
        
        # Build the full prompt with context
        if language == "en":
            prompt = f"""{base_prompt}

【Available Data】
- Market Analysis: {market_research_report}
- Sentiment Report: {sentiment_report}
- News Report: {news_report}
- Fundamentals Report: {fundamentals_report}
- Debate History: {history}
- Bullish Arguments: {current_response}
- Past Experience: {past_memory_str}

Please provide your bearish analysis now."""
        else:
            prompt = f"""{base_prompt}

【可用資源】
- 市場分析：{market_research_report}
- 社群情緒：{sentiment_report}
- 新聞：{news_report}
- 基本面：{fundamentals_report}
- 辯論歷史：{history}
- 看漲論點：{current_response}
- 過往經驗：{past_memory_str}

請提供您的看跌分析。"""

        response = llm.invoke(prompt)
        
        response.content = fix_common_llm_errors(response.content)
        validate_and_warn(response.content, "Bear_Researcher")

        # Format argument based on language
        if language == "en":
            argument = f"Bear Analyst: {response.content}"
        else:
            argument = f"看跌分析師：{response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node