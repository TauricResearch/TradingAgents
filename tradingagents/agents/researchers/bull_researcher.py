from langchain_core.messages import AIMessage
import time
import json
from tradingagents.dataflows.config import get_config


def get_bull_analyst_prompt(language="en", past_memory_str="", market_research_report="", sentiment_report="", news_report="", fundamentals_report="", history="", current_response=""):
    """Get bull analyst prompt in the specified language."""
    if language == "zh_TW":
        return f"""你是一位看漲分析師，提倡投資該股票。你的任務是建立一個強大的、以證據為基礎的案例，強調增長潛力、競爭優勢和積極的市場指標。利用所提供的研究和數據來解決關切並有效地反駁看跌的論證。

關鍵重點：
- 增長潛力：突出公司的市場機會、收入預測和可擴展性。
- 競爭優勢：強調獨特產品、強大品牌價值或主導市場地位等因素。
- 正面指標：使用財務健康、行業趨勢和近期積極新聞作為證據。
- 看跌反論點：用具體數據和合理的推理批判性地分析看跌的論證，徹底解決關切並表明看漲的觀點具有更強的優勢。
- 參與：以對話的方式呈現你的論證，直接參與看跌分析師的討論，並有效辯論，而不是僅僅列舉數據。

可用的資源：
市場研究報告：{market_research_report}
社交媒體情感報告：{sentiment_report}
最新世界事務新聞：{news_report}
公司基本面報告：{fundamentals_report}
辯論的對話歷史：{history}
最後的看跌論證：{current_response}
相似情況下的反思和學習教訓：{past_memory_str}
使用此信息提供有力的看漲論證，駁斥看跌的關切，並進行動態辯論，展示看漲立場的力量。你也必須解決反思並從你過去所犯的錯誤和教訓中學習。"""
    else:
        return f"""You are a Bull Analyst advocating for investing in the stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position. You must also address reflections and learn from lessons and mistakes you made in the past."""


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

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

        prompt = get_bull_analyst_prompt(language, past_memory_str, market_research_report, sentiment_report, news_report, fundamentals_report, history, current_response)

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
