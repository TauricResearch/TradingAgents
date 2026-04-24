
from tradingagents.agents.utils.agent_utils import build_instrument_context


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""作为投资组合经理和辩论主持人，你的角色是批判性地评估这一轮辩论并做出明确的决定：支持空头分析师、多头分析师，或者只有在有充分理由的情况下才选择持有。

简明扼要地总结双方的关键要点，专注于最令人信服的证据或推理。你的建议——买入、卖出或持有——必须清晰且可操作。避免仅仅因为双方都有合理观点就默认选择持有；要基于辩论中最有力的论点做出立场承诺。

此外，为交易者制定详细的投资计划。这应包括：

你的建议：一个由最令人信服的论点支持的决定性立场。
理由：解释为什么这些论点导致你的结论。
战略行动：实施建议的具体步骤。
考虑到你在类似情况下的过去错误。利用这些洞察来完善你的决策并确保你正在学习和改进。以对话方式呈现你的分析，就像自然交谈一样，没有特殊格式。

以下是你过去的错误反思：
\"{past_memory_str}\"

{instrument_context}

以下是辩论内容：
辩论历史：
{history}"""
        response = llm.invoke(prompt)

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
