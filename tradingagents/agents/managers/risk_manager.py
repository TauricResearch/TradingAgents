# -*- coding: utf-8 -*-
import time
import json
from tradingagents.agents.utils.output_filter import fix_common_llm_errors, validate_and_warn
from tradingagents.agents.utils.prompts import get_risk_manager_prompt


def create_risk_manager(llm, memory, language: str = "zh-TW"):
    """
    建立一個風險管理員（裁判）節點。

    Args:
        llm: 用於生成決策的語言模型。
        memory: 儲存過去情況和反思的記憶體物件。
        language: 報告語言 ('en' 或 'zh-TW')

    Returns:
        function: 一個代表風險管理員節點的函式。
    """

    def risk_manager_node(state) -> dict:
        """風險管理員節點的執行函式。"""
        company_name = state["company_of_interest"]
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state["history"]
        
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        
        past_memories = memory.get_memories(curr_situation, n_matches=2)
        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            recommendation = rec["recommendation"]
            past_memory_str += recommendation + "\n\n"

        # Get language-specific prompt
        base_prompt = get_risk_manager_prompt(language)
        
        if language == "en":
            prompt = f"""{base_prompt}

【Available Information】
- Past Reflections: "{past_memory_str}"
- Trader Plan: {trader_plan}
- Debate History: {history}

Please provide your risk management decision report."""
        else:
            prompt = f"""{base_prompt}

【可用資訊】
- 過去反思："{past_memory_str}"
- 交易員計畫：{trader_plan}
- 辯論歷史：{history}

請提供您的風險管理決策報告。"""

        response = llm.invoke(prompt)
        
        response.content = fix_common_llm_errors(response.content)
        validate_and_warn(response.content, "Risk_Manager")

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "risky_history": risk_debate_state["risky_history"],
            "safe_history": risk_debate_state["safe_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_risky_response": risk_debate_state["current_risky_response"],
            "current_safe_response": risk_debate_state["current_safe_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return risk_manager_node