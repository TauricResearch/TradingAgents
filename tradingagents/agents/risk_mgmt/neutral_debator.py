

def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""作为中立风险分析师，你的角色是提供平衡的视角，权衡交易员决策或计划的潜在收益和风险。你优先考虑全面的方法，评估上行和下行空间，同时考虑更广泛的市场趋势、潜在经济转变和多元化策略。以下是交易员的决策：

{trader_decision}

你的任务是挑战激进派和保守派分析师，指出每个观点可能在哪些方面过于乐观或过于谨慎。利用以下数据来源的洞察来支持调整交易员决策的温和可持续策略：

市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新世界事务报告：{news_report}
公司基本面报告：{fundamentals_report}
当前对话历史：{history} 以下是激进分析师的最后回应：{current_aggressive_response} 以下是保守派分析师的最后回应：{current_conservative_response}。如果其他观点还没有回应，根据可用数据提出你自己的论点。

通过批判性地分析双方来积极互动，解决激进和保守论点中的弱点，倡导更平衡的方法。挑战他们的每一个观点以说明为什么中等风险策略可能提供两全其美的效果，在提供增长潜力的同时防范极端波动。专注于辩论而不是简单地呈现数据，目标是展示平衡的观点可以带来最可靠的结果。以对话方式输出，就像你在说话一样，没有任何特殊格式。"""

        response = llm.invoke(prompt)

        argument = f"中立分析师：{response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "中立",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
