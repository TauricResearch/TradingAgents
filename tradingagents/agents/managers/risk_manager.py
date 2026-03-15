import time
import json
from tradingagents.dataflows.config import get_config


def get_risk_manager_prompt(language="en", past_memory_str="", history="", trader_plan=""):
    """Get risk manager prompt in the specified language."""
    if language == "zh_TW":
        return f"""作為風險管理評判官和辯論協調者，你的目標是評估三位風險分析師—激進型、中立型和保守型—之間的辯論，並為交易員確定最佳行動方案。你的決定必須產生明確的建議：買入、賣出或持有。只有在特定論證充分正當的情況下才選擇持有，不是在所有方面似乎都有效時的退路。力求清晰和決定性。

決策指南：
1. **總結關鍵論證**：從每位分析師中提取最有力的觀點，專注於與背景的相關性。
2. **提供理由**：用直接引用和來自辯論的反論證支持你的建議。
3. **完善交易員的計劃**：以交易員的原始計劃開始，**{trader_plan}**，並根據分析師的見解進行調整。
4. **從過去的錯誤中學習**：使用**{past_memory_str}**的經驗教訓來解決先前的誤判並改進你現在所做的決定，確保你沒有做出錯誤的買入/賣出/持有決定而虧錢。

交付物：
- 清晰且可行的建議：買入、賣出或持有。
- 以辯論和過去反思為基礎的詳細理由。

---

**分析師辯論歷史：**  
{history}

---

專注於可行的見解和持續改進。以過去的教訓為基礎，認真評估所有觀點，確保每項決定都推動更好的結果。"""
    else:
        return f"""As the Risk Management Judge and Debate Facilitator, your goal is to evaluate the debate between three risk analysts—Aggressive, Neutral, and Conservative—and determine the best course of action for the trader. Your decision must result in a clear recommendation: Buy, Sell, or Hold. Choose Hold only if strongly justified by specific arguments, not as a fallback when all sides seem valid. Strive for clarity and decisiveness.

Guidelines for Decision-Making:
1. **Summarize Key Arguments**: Extract the strongest points from each analyst, focusing on relevance to the context.
2. **Provide Rationale**: Support your recommendation with direct quotes and counterarguments from the debate.
3. **Refine the Trader's Plan**: Start with the trader's original plan, **{trader_plan}**, and adjust it based on the analysts' insights.
4. **Learn from Past Mistakes**: Use lessons from **{past_memory_str}** to address prior misjudgments and improve the decision you are making now to make sure you don't make a wrong BUY/SELL/HOLD call that loses money.

Deliverables:
- A clear and actionable recommendation: Buy, Sell, or Hold.
- Detailed reasoning anchored in the debate and past reflections.

---

**Analysts Debate History:**  
{history}

---

Focus on actionable insights and continuous improvement. Build on past lessons, critically evaluate all perspectives, and ensure each decision advances better outcomes."""


def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:

        company_name = state["company_of_interest"]

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        # Get language from config, default to English
        config = get_config()
        language = config.get("language", "en")

        prompt = get_risk_manager_prompt(language, past_memory_str, history, trader_plan)

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

    return risk_manager_node
