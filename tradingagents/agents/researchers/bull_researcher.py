

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

        prompt = f"""你是一位多头分析师，主张投资这只股票。你的任务是建立一个基于证据的强力案例，强调增长潜力、竞争优势和积极的市场指标。利用提供的研究和数据来解决问题并有效反驳空头观点。

需要关注的重点：
- 增长潜力：突出公司的市场机会、收入预测和可扩展性。
- 竞争优势：强调独特产品、强品牌或主导市场地位等因素。
- 积极指标：使用财务状况、行业趋势和近期正面新闻作为证据。
- 空头反驳点：用具体数据和合理推理批判性地分析空头论点，彻底解决问题并展示多头观点为何更具说服力。
- 互动交流：以对话方式呈现你的论点，直接回应空头分析师的观点并进行有效的辩论，而不仅仅是列出数据。

可用资源：
市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新世界事务新闻：{news_report}
公司基本面报告：{fundamentals_report}
辩论对话历史：{history}
上一个空头论点：{current_response}
类似情况的经验教训：{past_memory_str}
利用这些信息提供令人信服的多头论点，反驳空头的担忧，并进行展示多头立场优势的动态辩论。你还必须处理反思并从过去犯下的错误中吸取教训。
"""

        response = llm.invoke(prompt)

        argument = f"多头分析师：{response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
