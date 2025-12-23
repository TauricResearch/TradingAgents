# -*- coding: utf-8 -*-
import time
import json
from tradingagents.agents.utils.output_filter import fix_common_llm_errors, validate_and_warn
from tradingagents.agents.utils.prompts import get_aggressive_debator_prompt


def create_risky_debator(llm, language: str = "zh-TW"):
    """
    建立一個激進的風險辯論員節點。

    Args:
        llm: 用於生成回應的語言模型。
        language: 報告語言 ('en' 或 'zh-TW')

    Returns:
        function: 一個代表激進辯論員節點的函式。
    """

    def risky_node(state) -> dict:
        """激進辯論員節點的執行函式。"""
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        risky_history = risk_debate_state.get("risky_history", "")

        current_safe_response = risk_debate_state.get("current_safe_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        trader_decision = state["trader_investment_plan"]

        # Get language-specific prompt
        base_prompt = get_aggressive_debator_prompt(language)
        
        if language == "en":
            prompt = f"""{base_prompt}

【Available Information】
- Trader Plan: {trader_decision}
- Reports: {market_research_report}, {sentiment_report}, {news_report}, {fundamentals_report}
- Debate History: {history}
- Opponent Views: {current_safe_response}, {current_neutral_response}

Please provide your aggressive risk analysis."""
        else:
            prompt = f"""{base_prompt}

【可用資訊】
- 交易員計畫：{trader_decision}
- 各類報告：{market_research_report}, {sentiment_report}, {news_report}, {fundamentals_report}
- 辯論歷史：{history}
- 對手觀點：{current_safe_response}, {current_neutral_response}

請提供您的激進風險分析。"""

        response = llm.invoke(prompt)
        
        response.content = fix_common_llm_errors(response.content)
        validate_and_warn(response.content, "Aggressive_Debator")

        if language == "en":
            argument = f"Aggressive Analyst: {response.content}"
        else:
            argument = f"激進分析師：{response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risky_history + "\n" + argument,
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Risky",
            "current_risky_response": argument,
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return risky_node