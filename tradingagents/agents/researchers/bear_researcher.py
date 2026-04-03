from langchain_core.messages import AIMessage
import time
import json
from tradingagents.agents.utils.agent_utils import (
    build_debate_brief,
    extract_feedback_snapshot,
    get_language_instruction,
    get_localized_final_proposal_instruction,
    get_snapshot_template,
    get_snapshot_writing_instruction,
    localize_role_name,
    normalize_chinese_role_terms,
    strip_feedback_snapshot,
    truncate_for_prompt,
)


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        bear_history = investment_debate_state.get("bear_history", "")
        current_response = investment_debate_state.get("current_response", "")
        bull_snapshot = investment_debate_state.get("bull_snapshot", "")
        bear_snapshot = investment_debate_state.get("bear_snapshot", "")
        debate_brief = investment_debate_state.get("debate_brief", "")
        market_research_report = truncate_for_prompt(state["market_report"])
        sentiment_report = truncate_for_prompt(state["sentiment_report"])
        news_report = truncate_for_prompt(state["news_report"])
        fundamentals_report = truncate_for_prompt(state["fundamentals_report"])

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""You are a Bear Analyst making the case against investing in the stock. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Rolling debate brief: {debate_brief}
Your latest feedback snapshot: {bear_snapshot}
Latest bull feedback snapshot: {bull_snapshot}
Last bull argument body: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the stock. You must also address reflections and learn from lessons and mistakes you made in the past.
When writing in Chinese, use the exact role names "{localize_role_name('Bear Analyst')}" and "{localize_role_name('Bull Analyst')}". Do not use variants like "熊派分析师" or "牛派分析师".
Your main argument body must be written entirely in Chinese. {get_localized_final_proposal_instruction()}
After your normal argument, append an exact block using this template:
{get_snapshot_template()}
{get_snapshot_writing_instruction()}{get_language_instruction()}
"""

        response = llm.invoke(prompt)
        raw_content = normalize_chinese_role_terms(response.content)
        argument_body = strip_feedback_snapshot(raw_content)
        argument = f"{localize_role_name('Bear Analyst')}: {argument_body}"
        new_bear_snapshot = extract_feedback_snapshot(raw_content)
        new_debate_brief = build_debate_brief(
            {
                "Bull Analyst": bull_snapshot,
                "Bear Analyst": new_bear_snapshot,
            },
            latest_speaker="Bear Analyst",
        )

        new_investment_debate_state = {
            "history": investment_debate_state.get("history", "") + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "bull_snapshot": bull_snapshot,
            "bear_snapshot": new_bear_snapshot,
            "debate_brief": new_debate_brief,
            "latest_speaker": "Bear Analyst",
            "judge_decision": investment_debate_state.get("judge_decision", ""),
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
