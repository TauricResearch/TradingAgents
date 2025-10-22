import time
import json


def create_risky_debator(llm):
    def risky_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        risky_history = risk_debate_state.get("risky_history", "")

        current_safe_response = risk_debate_state.get("current_safe_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""作为风险型风险分析师，您的角色是积极倡导高回报、高风险的机会，强调大胆的策略和竞争优势。在评估交易员的决策或计划时，要专注于潜在的上行空间、增长潜力和创新收益——即使这些伴随着较高的风险。利用提供的市场数据和情绪分析来强化您的论点，并挑战相反的观点。具体而言，直接回应保守派和中立派分析师提出的每一个观点，用数据驱动的反驳和有说服力的推理进行反驳。突出他们的谨慎可能会错过关键机会的地方，或者他们的假设可能过于保守的地方。以下是交易员的决策：

{trader_decision}

您的任务是通过质疑和批判保守和中立立场，为交易员的决策创造一个令人信服的案例，以证明为什么您的高回报观点提供了最佳的前进道路。将以下来源的见解融入您的论点：

市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新世界事务报告：{news_report}
公司基本面报告：{fundamentals_report}
以下是当前对话历史：{history} 以下是保守派分析师的最新论点：{current_safe_response} 以下是中立派分析师的最新论点：{current_neutral_response}。如果其他观点没有回应，不要虚构内容，只需陈述您的观点。

通过解决提出的任何具体问题，驳斥他们逻辑中的弱点，并断言冒险以超越市场规范的好处来积极参与。专注于辩论和说服，而不仅仅是呈现数据。挑战每个对立观点，以强调为什么高风险方法是最佳的。以对话方式输出，就像您在没有任何特殊格式的情况下说话一样。"""

        response = llm.invoke(prompt)

        argument = f"Risky Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risky_history + "\n" + argument,
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Risky",
            "current_risky_response": argument,
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return risky_node
