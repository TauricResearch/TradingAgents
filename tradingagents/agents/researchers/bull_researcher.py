from langchain_core.messages import AIMessage
import time
import json


# 定义一个创建“看多”研究员（Bull Researcher）节点的工厂函数
def create_bull_researcher(llm, memory):
    """
    创建看多分析师（Bull Analyst）的 LangGraph 节点函数。

    Args:
        llm: 语言模型实例，用于生成分析和论点。
        memory: 外部记忆/检索系统，用于获取历史经验和教训。

    Returns:
        Callable: 接受当前状态并返回更新后的状态的节点函数 (bull_node)。
    """

    # 内部定义的节点函数，接收整个状态字典
    def bull_node(state) -> dict:
        """
        看多分析师节点的核心逻辑。
        根据全局状态中的报告和辩论历史，生成看多论点并更新状态。
        """
        # --- 1. 获取当前状态数据 ---
        investment_debate_state = state["investment_debate_state"]

        # 提取辩论的完整历史和上一轮空头（Bear）的回复
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")
        current_response = investment_debate_state.get("current_response", "")

        # 提取所有研究报告作为论证的证据
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        # --- 2. 记忆检索与格式化 ---
        # 合并所有报告，作为检索记忆的查询
        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # 从外部记忆中检索历史记录/教训
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        # 格式化检索到的历史教训，作为 Prompt 的一部分
        past_memory_str = ""
        for rec in past_memories:
            # 假设每个记忆记录包含一个 "recommendation" 字段
            past_memory_str += rec.get("recommendation", "") + "\n\n"

        # --- 3. 构建 Prompt 并调用 LLM ---
        # 构建发送给 LLM 的提示（Prompt），指导其扮演看多分析师的角色
        prompt = f"""You are a Bull Analyst advocating for investing in the stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

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
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position. You must also address reflections and learn from lessons and mistakes you made in the past.
"""

        # 调用 LLM 生成看多分析师的回复
        response = llm.invoke(prompt)

        # 格式化看多分析师的论点，加上身份前缀
        argument = f"Bull Analyst: {response.content}"

        # --- 4. 更新全局状态 ---
        new_investment_debate_state = {
            # 更新完整的辩论历史
            "history": history + "\n" + argument,
            # 更新看多方的历史记录 (便于后续总结)
            "bull_history": bull_history + "\n" + argument,
            # 保持看空方的历史不变 (从旧状态中获取)
            "bear_history": investment_debate_state.get("bear_history", ""),
            # 将当前回复设置为看多方的论点，供下一轮（如看空方）使用
            "current_response": argument,
            # 增加辩论的轮数计数
            "count": investment_debate_state["count"] + 1,
        }

        # 返回包含更新后的投资辩论状态的字典，用于 LangGraph 传递
        return {"investment_debate_state": new_investment_debate_state}

    # 返回定义的节点函数 (工厂函数模式)
    return bull_node