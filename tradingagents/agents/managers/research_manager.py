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

        # 根据配置选择语言
        config = getattr(memory, 'config', {})
        if config.get("output_language", "english") == "chinese":
            prompt = f"""作为投资组合经理和辩论主持人，你的任务是批判性地评估这轮辩论并做出明确决定：与看跌分析师保持一致、与看涨分析师保持一致，或者只有在基于所提出的论点有强有力的理由时才选择持有。

简洁地总结双方的关键观点，专注于最有说服力的证据或推理。你的建议——买入、卖出或持有——必须清晰且可行。避免仅仅因为双方都有有效观点就默认选择持有；根据辩论中最强有力的论点做出承诺立场。

此外，为交易员制定详细的投资计划。这应该包括：

你的建议：基于最有说服力论点的明确立场。
理由：解释为什么这些论点导致你的结论。
战略行动：实施建议的具体步骤。
考虑你在类似情况下的过去错误。利用这些洞察来完善你的决策制定，确保你正在学习和改进。以对话的方式呈现你的分析，就像自然地说话一样，不需要特殊格式。

以下是你对错误的过去反思：
\"{past_memory_str}\"

以下是辩论：
辩论历史：
{history}"""
        else:
            prompt = f"""As the portfolio manager and debate facilitator, your role is to critically evaluate this round of debate and make a definitive decision: align with the bear analyst, the bull analyst, or choose Hold only if it is strongly justified based on the arguments presented.

Summarize the key points from both sides concisely, focusing on the most compelling evidence or reasoning. Your recommendation—Buy, Sell, or Hold—must be clear and actionable. Avoid defaulting to Hold simply because both sides have valid points; commit to a stance grounded in the debate's strongest arguments.

Additionally, develop a detailed investment plan for the trader. This should include:

Your Recommendation: A decisive stance supported by the most convincing arguments.
Rationale: An explanation of why these arguments lead to your conclusion.
Strategic Actions: Concrete steps for implementing the recommendation.
Take into account your past mistakes on similar situations. Use these insights to refine your decision-making and ensure you are learning and improving. Present your analysis conversationally, as if speaking naturally, without special formatting. 

Here are your past reflections on mistakes:
\"{past_memory_str}\"

Here is the debate:
Debate History:
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
