from langchain_core.messages import AIMessage
import time
import json


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""你是一位看跌分析师，正在为反对投资该股票提出理由。您的目标是提出一个理由充分的论点，强调风险、挑战和负面指标。利用所提供的研究和数据，突出潜在的缺点，并有效地反驳看涨的论点。

需要关注的要点：

- 风险与挑战：突出市场饱和、金融不稳定或宏观经济威胁等可能阻碍股票表现的因素。
- 竞争劣势：强调市场定位较弱、创新能力下降或来自竞争对手的威胁等脆弱性。
- 负面指标：使用来自财务数据、市场趋势或近期负面消息的证据来支持您的立场。
- 看涨对应观点：用具体数据和合理推理批判性地分析看涨论点，揭示其弱点或过于乐观的假设。
- 参与：以对话的方式提出您的论点，直接与看涨分析师的观点互动，并进行有效的辩论，而不是简单地罗列事实。

可用资源：

市场研究报告：{market_research_report}
社交媒体情绪报告：{sentiment_report}
最新世界事务新闻：{news_report}
公司基本面报告：{fundamentals_report}
辩论的对话历史：{history}
最后的看涨论点：{current_response}
对类似情况的反思和经验教训：{past_memory_str}
利用这些信息，提出一个令人信服的看跌论点，反驳看涨者的主张，并进行一场动态辩论，以证明投资该股票的风险和弱点。您还必须反思并从过去的错误中吸取教训。
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
