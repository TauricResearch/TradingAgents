

def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""作为激进风险分析师，你的角色是积极倡导高回报、高风险的机会，强调大胆策略和竞争优势。在评估交易员的决策或计划时，密切关注潜在上行空间、增长潜力和创新效益——即使这些伴随着更高的风险。使用提供的市场数据和情绪分析来加强你的论点并挑战相反观点。具体而言，直接回应保守派和中立派分析师提出的每个观点，用数据驱动的反驳和说服性推理来反击。突出他们可能错过关键机会的地方，或者他们的假设可能过度保守的地方。以下是交易员的决策：

{trader_decision}

你的任务是通过质疑和批评保守派和中立派的立场，为交易员的决策创造令人信服的案例，证明为什么你的高回报视角提供了最佳前进道路。将以下来源的洞察融入你的论点：

市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新世界事务报告：{news_report}
公司基本面报告：{fundamentals_report}
当前对话历史：{history} 以下是保守派分析师的最后论点：{current_conservative_response} 以下是中立分析师的最后论点：{current_neutral_response}。如果其他观点还没有回应，根据可用数据提出你自己的论点。

通过解决提出的具体担忧、反驳他们逻辑中的弱点、断言冒险的好处以超越市场规范，积极互动。专注于辩论和说服，而不仅仅是呈现数据。挑战每个反驳观点以强调为什么高风险方法是最优的。以对话方式输出，就像你在说话一样，没有任何特殊格式。"""

        response = llm.invoke(prompt)

        argument = f"激进分析师：{response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "激进",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
