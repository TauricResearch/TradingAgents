import functools

from tradingagents.agents.utils.agent_utils import build_instrument_context


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        context = {
            "role": "user",
            "content": f"基于分析师团队的全面分析，这是为{company_name}量身定制的投资计划。{instrument_context} 该计划整合了当前技术市场趋势、宏观经济指标和社交媒体情绪的洞察。以此计划为基础评估你的下一个交易决策。\n\n建议投资计划：{investment_plan}\n\n利用这些洞察做出明智和战略性的决策。",
        }

        messages = [
            {
                "role": "system",
                "content": f"""你是一位分析市场数据并做出投资决策的交易代理。基于你的分析，提供具体的买入、卖出或持有建议。以坚定决策结束，并始终以"**最终交易提案：买入/持有/卖出**"结束你的回复以确认你的建议。应用过去决策中的教训来加强你的分析。以下是你在类似情况下交易的教训和经验：{past_memory_str}""",
            },
            context,
        ]

        result = llm.invoke(messages)

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="交易员")
