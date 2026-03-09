from langchain_core.messages import AIMessage
import time
import json
from tradingagents.dataflows.config import get_config


def get_bear_analyst_prompt(language="en", past_memory_str="", market_research_report="", sentiment_report="", news_report="", fundamentals_report="", history="", current_response=""):
    """Get bear analyst prompt in the specified language."""
    if language == "zh_TW":
        return f"""你是一位看跌分析師，論證反對投資該股票。你的目標是呈現一個精心推理的論證，強調風險、挑戰和負面指標。利用所提供的研究和數據來突出潛在的下行風險並有效地反駁看漲的論證。

關鍵重點：

- 風險和挑戰：突出可能阻礙股票表現的因素，如市場飽和、財務不穩定或宏觀經濟威脅。
- 競爭劣勢：強調弱點，如較弱的市場地位、創新下降或來自競爭對手的威脅。
- 負面指標：使用來自財務數據、市場趨勢或近期不利新聞的證據來支持你的立場。
- 看漲反論點：用具體數據和合理的推理批判性地分析看漲的論證，揭露弱點或過度樂觀的假設。
- 參與：以對話的方式呈現你的論證，直接參與看漲分析師的討論，並有效辯論，而不是簡單地列舉事實。

可用的資源：

市場研究報告：{market_research_report}
社交媒體情感報告：{sentiment_report}
最新世界事務新聞：{news_report}
公司基本面報告：{fundamentals_report}
辯論的對話歷史：{history}
最後的看漲論證：{current_response}
相似情況下的反思和學習教訓：{past_memory_str}
使用此信息提供有力的看跌論證，駁斥看漲的主張，並進行動態辯論，展示投資該股票的風險和弱點。你也必須解決反思並從你過去所犯的錯誤和教訓中學習。"""
    else:
        return f"""You are a Bear Analyst making the case against investing in the stock. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the stock. You must also address reflections and learn from lessons and mistakes you made in the past."""


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
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
            past_memory_str += rec["recommendation"] + "\n\n"

        # Get language from config, default to English
        config = get_config()
        language = config.get("language", "en")

        prompt = get_bear_analyst_prompt(language, past_memory_str, market_research_report, sentiment_report, news_report, fundamentals_report, history, current_response)

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
