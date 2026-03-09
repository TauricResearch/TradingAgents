import time
import json
from tradingagents.dataflows.config import get_config


def get_aggressive_analyst_prompt(language="en", trader_decision="", market_research_report="", sentiment_report="", news_report="", fundamentals_report="", history="", current_conservative_response="", current_neutral_response=""):
    """Get aggressive risk analyst prompt in the specified language."""
    if language == "zh_TW":
        return f"""作為激進風險分析師，你的角色是積極擁護高回報、高風險的機會，強調大膽戰略和競爭優勢。在評估交易員的決定或計劃時，要密切關注潛在的上行空間、增長潛力和創新優勢—即使這些伴隨著更高的風險。使用所提供的市場數據和情感分析來加強你的論證並挑戰相反的觀點。具體來說，直接回應保守派和中立分析師的每一點，用數據驅動的反駁和有說服力的推理進行對抗。突出他們的謹慎可能錯過的關鍵機會，或他們的假設可能過度保守的地方。以下是交易員的決定：

{trader_decision}

你的任務是通過質疑和批評保守派和中立的立場，為交易員的決定創造一個令人信服的案例，以證明你的高回報觀點提供了前進的最佳途徑。將以下來源的見解納入你的論證：

市場研究報告：{market_research_report}
社交媒體情感報告：{sentiment_report}
最新世界事務報告：{news_report}
公司基本面報告：{fundamentals_report}
這是當前的對話歷史：{history}
保守派分析師的最後論證：{current_conservative_response}
中立派分析師的最後論證：{current_neutral_response}。如果沒有來自其他觀點的回應，請不要幻想，只是呈現你的觀點。

通過解決任何提出的具體關切、駁斥他們邏輯中的弱點，並主張風險承擔的優勢來超越市場規範，主動參與。保持專注於辯論和說服，而不僅僅是呈現數據。挑戰他們的每一個反論點，以強調為什麼高風險的方法是最優的。以自然對話的方式輸出，無需任何特殊格式。"""
    else:
        return f"""As the Aggressive Risk Analyst, your role is to actively champion high-reward, high-risk opportunities, emphasizing bold strategies and competitive advantages. When evaluating the trader's decision or plan, focus intently on the potential upside, growth potential, and innovative benefits—even when these come with elevated risk. Use the provided market data and sentiment analysis to strengthen your arguments and challenge the opposing views. Specifically, respond directly to each point made by the conservative and neutral analysts, countering with data-driven rebuttals and persuasive reasoning. Highlight where their caution might miss critical opportunities or where their assumptions may be overly conservative. Here is the trader's decision:

{trader_decision}

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances to demonstrate why your high-reward perspective offers the best path forward. Incorporate insights from the following sources into your arguments:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here are the last arguments from the conservative analyst: {current_conservative_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints, do not hallucinate and just present your point.

Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of risk-taking to outpace market norms. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why a high-risk approach is optimal. Output conversationally as if you are speaking without any special formatting."""


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        # Get language from config, default to English
        config = get_config()
        language = config.get("language", "en")

        prompt = get_aggressive_analyst_prompt(language, trader_decision, market_research_report, sentiment_report, news_report, fundamentals_report, history, current_conservative_response, current_neutral_response)

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
