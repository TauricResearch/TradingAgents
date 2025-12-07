from langchain_core.messages import AIMessage
import time
import json


# 定义一个创建“看空”研究员（Bear Researcher）节点的工厂函数
def create_bear_researcher(llm, memory):
    """
    创建看空分析师（Bear Analyst）的 LangGraph 节点函数。

    Args:
        llm: 语言模型实例，用于生成分析和论点。
        memory: 外部记忆/检索系统，用于获取历史教训。

    Returns:
        Callable: 接受当前状态并返回更新后的状态的节点函数 (bear_node)。
    """

    def bear_node(state) -> dict:
        """
        看空分析师节点的核心逻辑。
        根据全局状态中的报告和辩论历史，生成看空论点并更新状态。
        """
        # --- 1. 获取当前状态数据 ---
        investment_debate_state = state["investment_debate_state"]

        # 提取辩论历史和上一轮多头（Bull）的回复
        history = investment_debate_state.get("history", "")
        current_response = investment_debate_state.get("current_response", "")

        # 提取所有研究报告作为论证的证据
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        # --- 2. 记忆检索与格式化 ---
        # 合并所有报告，作为检索记忆的查询（寻找相似情况下的历史教训）
        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # 从外部记忆中检索历史记录/教训
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        # 格式化检索到的历史教训，作为 Prompt 的一部分
        past_memory_str = ""
        for rec in past_memories:
            past_memory_str += rec.get("recommendation", "") + "\n\n"

        # --- 3. 构建 Prompt 并调用 LLM ---
        prompt = f"""You are a Bear Analyst making the case against investing in the stock. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:
- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}

Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the stock. You must also address reflections and learn from lessons and mistakes you made in the past.
"""

        # 调用 LLM 生成看空分析师的回复
        response = llm.invoke(prompt)

        # 格式化看空分析师的论点，加上身份前缀
        argument = f"Bear Analyst: {response.content}"

        # --- 4. 更新全局状态 ---
        new_investment_debate_state = {
            # 更新完整的辩论历史
            "history": history + "\n" + argument,
            # 更新看空方的历史记录 (便于后续总结和自我反思)
            "bear_history": investment_debate_state.get("bear_history", "") + "\n" + argument,
            # 将当前回复设置为看空方的论点，供下一轮（如看多方）使用
            "current_response": argument,
            # 增加辩论的轮数计数
            "count": investment_debate_state["count"] + 1,
            # 保持看多方的历史不变 (从旧状态中获取)
            "bull_history": investment_debate_state.get("bull_history", ""),
        }

        # 返回包含更新后的投资辩论状态的字典，用于 LangGraph 传递
        return {"investment_debate_state": new_investment_debate_state}

    # 返回定义的节点函数
    return bear_node
