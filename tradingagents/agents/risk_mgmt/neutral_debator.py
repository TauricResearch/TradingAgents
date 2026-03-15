import time
import json
from tradingagents.dataflows.config import get_config


def get_neutral_analyst_prompt(language="en", trader_decision="", market_research_report="", sentiment_report="", news_report="", fundamentals_report="", history="", current_aggressive_response="", current_conservative_response=""):
    """Get neutral risk analyst prompt in the specified language."""
    if language == "zh_TW":
        return f"""作為中立風險分析師，你的角色是提供平衡的觀點，權衡交易員決定或計劃的潛在利益和風險。你優先考慮全面的方法，評估優缺點，同時考慮更廣泛的市場趨勢、潛在的經濟轉變和多元化戰略。以下是交易員的決定：

{trader_decision}

你的任務是挑戰激進派和保守派分析師，指出每個觀點可能過度樂觀或過度謹慎的地方。從以下數據來源中使用見解，以支持溫和、可持續的戰略來調整交易員的決定：

市場研究報告：{market_research_report}
社交媒體情感報告：{sentiment_report}
最新世界事務報告：{news_report}
公司基本面報告：{fundamentals_report}
這是當期的對話歷史：{history}
激進派分析師的最後回應：{current_aggressive_response}
保守派分析師的最後回應：{current_conservative_response}。如果沒有來自其他觀點的回應，請不要幻想，只是呈現你的觀點。

通過分析激進派和保守派論證中的弱點，主動參與，解決他們的每一個觀點，以倡導更平衡的方法。挑戰他們的每一個觀點，以說明溫和的風險戰略可能如何提供兩全其美—提供增長潛力，同時防止極端波動。專注於辯論而不是簡單呈現數據，目的是展示平衡的看法如何能導致最可靠的結果。以自然對話的方式輸出，無需任何特殊格式。"""
    else:
        return f"""As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. You prioritize a well-rounded approach, evaluating the upsides and downsides while factoring in broader market trends, potential economic shifts, and diversification strategies.Here is the trader's decision:

{trader_decision}

Your task is to challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious. Use insights from the following data sources to support a moderate, sustainable strategy to adjust the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the conservative analyst: {current_conservative_response}. If there are no responses from the other viewpoints, do not hallucinate and just present your point.

Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Challenge each of their points to illustrate why a moderate risk strategy might offer the best of both worlds, providing growth potential while safeguarding against extreme volatility. Focus on debating rather than simply presenting data, aiming to show that a balanced view can lead to the most reliable outcomes. Output conversationally as if you are speaking without any special formatting."""


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        # Get language from config, default to English
        config = get_config()
        language = config.get("language", "en")

        prompt = get_neutral_analyst_prompt(language, trader_decision, market_research_report, sentiment_report, news_report, fundamentals_report, history, current_aggressive_response, current_conservative_response)

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
