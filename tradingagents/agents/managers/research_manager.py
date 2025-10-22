import time
import json


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
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

        prompt = f"""作为投资组合经理和辩论主持人，您的角色是批判性地评估本轮辩论并做出明确的决定：与空头分析师、多头分析师保持一致，或者仅在有充分理由支持的情况下选择持有。

简明扼要地总结双方的要点，重点关注最有说服力的证据或推理。您的建议——买入、卖出或持有——必须清晰且可操作。避免仅仅因为双方都有道理就默认持有；致力于基于辩论中最有力论点的立场。

此外，为交易员制定详细的投资计划。这应包括：

您的建议：一个由最有说服力的论点支持的果断立场。
基本原理：解释为什么这些论点会得出您的结论。
战略行动：实施建议的具体步骤。
考虑您过去在类似情况下的错误。利用这些见解来完善您的决策，并确保您正在学习和进步。以对话方式呈现您的分析，就像自然说话一样，无需特殊格式。 

以下是您过去对错误的思考：
\"{past_memory_str}\"

这是辩论：
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
