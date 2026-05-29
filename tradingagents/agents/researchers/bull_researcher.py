
from tradingagents.agents.utils.agent_utils import (
    DEBATE_EVIDENCE_GUARDRAIL,
    get_language_instruction,
    truncate_history,
)
from tradingagents.agents.utils.conflict_detector import format_conflict_report_for_prompt


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = truncate_history(investment_debate_state.get("history", ""))
        bull_history = investment_debate_state.get("bull_history", "")

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

        memory_section = (
            f"Reflections from similar situations and lessons learned: {past_memory_str}\n"
            if past_memory_str else ""
        )

        conflict_block = format_conflict_report_for_prompt(state.get("conflict_report"))

        prompt = f"""You are a Bull Analyst. Make a concise, evidence-based case for investing in the stock, directly countering the bear's latest argument. Speak conversationally.

Market report: {market_research_report}
Sentiment report: {sentiment_report}
News report: {news_report}
Fundamentals report: {fundamentals_report}
Debate history: {history}
Last bear argument: {current_response}{conflict_block}
{memory_section}{DEBATE_EVIDENCE_GUARDRAIL}{get_language_instruction()}"""

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
