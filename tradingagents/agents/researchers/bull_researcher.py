from langchain_core.messages import AIMessage
import time
import json


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

        prompt = f"""你是一位看涨分析师，主张投资该股票。你的任务是建立一个强有力的、以证据为基础的案例，强调增长潜力、竞争优势和积极的市场指标。利用所提供的研究和数据，有效解决疑虑并反驳看跌论点。

重点关注：
- 增长潜力：突出公司的市场机会、收入预测和可扩展性。
- 竞争优势：强调独特产品、强大品牌或主导市场地位等因素。
- 积极指标：以财务健康、行业趋势和近期利好消息为证。
- 看跌对策：用具体数据和合理推理批判性地分析看跌论点，彻底解决疑虑，并说明为什么看涨观点更具优势。
- 参与：以对话方式呈现你的论点，直接与看跌分析师的观点交锋，有效辩论，而不仅仅是罗列数据。

可用资源：
市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新世界事务新闻：{news_report}
公司基本面报告：{fundamentals_report}
辩论的对话历史：{history}
最新的看跌论点：{current_response}
类似情况的反思和经验教训：{past_memory_str}
利用这些信息，提出一个令人信服的看涨论点，驳斥看跌者的担忧，并进行一场动态辩论，展示看涨立场的优势。你还必须反思并从过去的错误和教训中学习。
"""

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
