from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction


def create_portfolio_manager(llm, memory):
    def portfolio_manager_node(state) -> dict:

        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""作为投资组合经理，综合风险分析师的辩论并交付最终交易决策。

{instrument_context}

---

**评级量表**（严格使用其中之一）：
- **买入**：强烈信念入场或加仓
- **增持**：看好前景，逐步增加敞口
- **持有**：维持当前仓位，无需操作
- **减仓**：减少敞口，获取部分利润
- **卖出**：清仓或避免入场

**背景：**
- 研究经理的投资计划：*{research_plan}*
- 交易员的交易提案：*{trader_plan}*
- 过去决策的经验教训：*{past_memory_str}*

**必需输出结构：**
1. **评级**：声明买入/增持/持有/减仓/卖出之一。
2. **执行摘要**：涵盖入场策略、仓位规模、关键风险水平和时间范围的简明行动计划。
3. **投资论点**：基于分析师辩论和过去反思的详细推理。

---

**风险分析师辩论历史：**
{history}

---

做出决定性的决策，让每个结论都基于分析师提供的具体证据。"""

        response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return portfolio_manager_node
