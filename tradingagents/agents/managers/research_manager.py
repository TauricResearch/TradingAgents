import time
import json
from tradingagents.dataflows.config import get_config


def get_research_manager_prompt(language="en", past_memory_str="", history=""):
    """Get research manager prompt in the specified language."""
    if language == "zh_TW":
        return f"""作為投資組合經理和辯論協調者，你的角色是認真評估這一輪辯論，做出明確的決定：贊同熊市分析師、看漲分析師，或選擇持有（只有在基於所呈現的論證得到充分理由證實的情況下）。

簡明扼要地總結雙方的關鍵點，專注於最有說服力的證據或推理。你的建議—買入、賣出或持有—必須清晰且可行。避免默認選擇持有，僅因為雙方都有有效的觀點；根據辯論中最有力的論證形成立場。

此外，為交易員制定詳細的投資計劃。這應包括：

你的建議：由最令人信服的論證支持的決定性立場。
理由：解釋為什麼這些論證導致你的結論。
戰略行動：實施該建議的具體步驟。
考慮你在類似情況下過去的錯誤。利用這些見解來完善你的決策，確保你在學習和改進。以自然對話的方式呈現你的分析，無需特殊格式。

這是你過去關於類似情況的錯誤反思：
\"{past_memory_str}\"

以下是辯論：
辯論歷史：
{history}"""
    else:
        return f"""As the portfolio manager and debate facilitator, your role is to critically evaluate this round of debate and make a definitive decision: align with the bear analyst, the bull analyst, or choose Hold only if it is strongly justified based on the arguments presented.

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

        # Get language from config, default to English
        config = get_config()
        language = config.get("language", "en")

        prompt = get_research_manager_prompt(language, past_memory_str, history)
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
