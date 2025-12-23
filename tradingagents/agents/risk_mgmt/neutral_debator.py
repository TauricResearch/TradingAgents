# -*- coding: utf-8 -*-
import time
import json
from tradingagents.agents.utils.output_filter import fix_common_llm_errors, validate_and_warn
from tradingagents.agents.utils.prompts import get_neutral_debator_prompt


def create_neutral_debator(llm, language: str = "zh-TW"):
    """
    建立一個中立的風險辯論員節點。

    Args:
        llm: 用於生成回應的語言模型。
        language: 報告語言 ('en' 或 'zh-TW')

    Returns:
        function: 一個代表中立辯論員節點的函式。
    """

    def neutral_node(state) -> dict:
        """中立辯論員節點的執行函式。"""
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_safe_response = risk_debate_state.get("current_safe_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        trader_decision = state["trader_investment_plan"]

        # Get language-specific prompt
        base_prompt = get_neutral_debator_prompt(language)
        
        if language == "en":
            prompt = f"""{base_prompt}

【Available Information】
- Trader Plan: {trader_decision}
- Reports: {market_research_report}, {sentiment_report}, {news_report}, {fundamentals_report}
- Debate History: {history}
- Opponent Views: {current_risky_response}, {current_safe_response}

Please provide your neutral risk analysis."""
        else:
            prompt = f"""{base_prompt}

【可用資訊】
- 交易員計畫：{trader_decision}
- 各類報告：{market_research_report}, {sentiment_report}, {news_report}, {fundamentals_report}
- 辯論歷史：{history}
- 對手觀點：{current_risky_response}, {current_safe_response}

請提供您的中立風險分析。"""

        response = llm.invoke(prompt)
        
        response.content = fix_common_llm_errors(response.content)
        validate_and_warn(response.content, "Neutral_Debator")

        if language == "en":
            argument = f"Neutral Analyst: {response.content}"
        else:
            argument = f"中立分析師：{response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "neutral_history": neutral_history + "\n" + argument,
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": risk_debate_state.get("safe_history", ""),
            "latest_speaker": "Neutral",
            "current_neutral_response": argument,
            "current_risky_response": risk_debate_state.get("current_risky_response", ""),
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node