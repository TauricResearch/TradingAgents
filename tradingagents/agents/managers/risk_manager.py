import time
import json


def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:

        company_name = state["company_of_interest"]

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["news_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""作为风险管理法官和辩论主持人，您的目标是评估三位风险分析师（风险、中立和安全/保守）之间的辩论，并确定交易员的最佳行动方案。您的决定必须产生明确的建议：买入、卖出或持有。仅当有特定论点充分证明时才选择持有，而不是在各方似乎都有效时的后备方案。力求清晰和果断。

决策指南：
1. **总结关键论点**：从每位分析师中提取最强有力的观点，重点关注与背景的相关性。
2. **提供理由**：用辩论中的直接引述和反驳来支持您的建议。
3. **完善交易员的计划**：从交易员的原始计划 **{trader_plan}** 开始，并根据分析师的见解进行调整。
4. **从过去的错误中学习**：利用 **{past_memory_str}** 中的经验教训来解决先前的错误判断，并改进您现在正在做出的决定，以确保您不会做出错误的买入/卖出/持有决策而亏钱。

可交付成果：
- 清晰可行的建议：买入、卖出或持有。
- 基于辩论和过去反思的详细推理。

---

**分析师辩论历史：**  
{history}

---

专注于可行的见解和持续改进。借鉴过去的经验教训，批判性地评估所有观点，并确保每项决策都能带来更好的结果。"""

        response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "risky_history": risk_debate_state["risky_history"],
            "safe_history": risk_debate_state["safe_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_risky_response": risk_debate_state["current_risky_response"],
            "current_safe_response": risk_debate_state["current_safe_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return risk_manager_node
