from langchain_core.messages import AIMessage
import time
import json
from tradingagents.dataflows.config import get_config


def get_conservative_analyst_prompt(language="en", trader_decision="", market_research_report="", sentiment_report="", news_report="", fundamentals_report="", history="", current_aggressive_response="", current_neutral_response=""):
    """Get conservative risk analyst prompt in the specified language."""
    if language == "zh_TW":
        return f"""作為保守風險分析師，你的主要目標是保護資產、最小化波動性，並確保穩定、可靠的增長。你優先考慮穩定性、安全性和風險緩解，仔細評估潛在損失、經濟衰退和市場波動。在評估交易員的決定或計劃時，認真審查高風險元素，指出決定可能使公司面臨不必要的風險，以及更謹慎的替代方案如何能確保長期收益。以下是交易員的決定：

{trader_decision}

你的任務是積極反駁激進派分析師和中立派分析師的論證，突出他們的看法可能如何忽視潛在威脅或未能優先考慮可持續性。直接回應他們的觀點，並從以下數據來源中提取大量證據，來建立一個令人信服的低風險方法案例，以調整交易員的決定：

市場研究報告：{market_research_report}
社交媒體情感報告：{sentiment_report}
最新世界事務報告：{news_report}
公司基本面報告：{fundamentals_report}
這是當期的對話歷史：{history}
激進派分析師的最後回應：{current_aggressive_response}
中立派分析師的最後回應：{current_neutral_response}。如果沒有來自其他觀點的回應，請不要幻想，只是呈現你的觀點。

通過質疑他們的樂觀主義並強調他們可能忽視的潛在下行風險來參與。解決他們的每一個反論點，以展示為什麼保守的立場最終是公司資產的最安全途徑。專注於辯論和批評他們的論證，以展示低風險戰略相對於他們的方法的力量。以自然對話的方式輸出，無需任何特殊格式。"""
    else:
        return f"""As the Conservative Risk Analyst, your primary objective is to protect assets, minimize volatility, and ensure steady, reliable growth. You prioritize stability, security, and risk mitigation, carefully assessing potential losses, economic downturns, and market volatility. When evaluating the trader's decision or plan, critically examine high-risk elements, pointing out where the decision may expose the firm to undue risk and where more cautious alternatives could secure long-term gains. Here is the trader's decision:

{trader_decision}

Your task is to actively counter the arguments of the Aggressive and Neutral Analysts, highlighting where their views may overlook potential threats or fail to prioritize sustainability. Respond directly to their points, drawing from the following data sources to build a convincing case for a low-risk approach adjustment to the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints, do not hallucinate and just present your point.

Engage by questioning their optimism and emphasizing the potential downsides they may have overlooked. Address each of their counterpoints to showcase why a conservative stance is ultimately the safest path for the firm's assets. Focus on debating and critiquing their arguments to demonstrate the strength of a low-risk strategy over their approaches. Output conversationally as if you are speaking without any special formatting."""


def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        # Get language from config, default to English
        config = get_config()
        language = config.get("language", "en")

        prompt = get_conservative_analyst_prompt(language, trader_decision, market_research_report, sentiment_report, news_report, fundamentals_report, history, current_aggressive_response, current_neutral_response)

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
