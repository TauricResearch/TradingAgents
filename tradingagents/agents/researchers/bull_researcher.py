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


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        bull_history = investment_debate_state.get("bull_history", "")
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

        prompt = f"""You are a Bull Analyst advocating for investing in the stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Rolling debate brief: {debate_brief}
Your latest feedback snapshot: {bull_snapshot}
Latest bear feedback snapshot: {bear_snapshot}
Last bear argument body: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position. You must also address reflections and learn from lessons and mistakes you made in the past.
When writing in Chinese, use the exact role names "{localize_role_name('Bull Analyst')}" and "{localize_role_name('Bear Analyst')}". Do not use variants like "牛派分析师" or "熊派分析师".
Your main argument body must be written entirely in Chinese. {get_localized_final_proposal_instruction()}
After your normal argument, append an exact block using this template:
{get_snapshot_template()}
{get_snapshot_writing_instruction()}{get_language_instruction()}
"""

        response = llm.invoke(prompt)
        raw_content = normalize_chinese_role_terms(response.content)
        argument_body = strip_feedback_snapshot(raw_content)
        argument = f"{localize_role_name('Bull Analyst')}: {argument_body}"
        new_bull_snapshot = extract_feedback_snapshot(raw_content)
        new_debate_brief = build_debate_brief(
            {
                "Bull Analyst": new_bull_snapshot,
                "Bear Analyst": bear_snapshot,
            },
            latest_speaker="Bull Analyst",
        )

        new_investment_debate_state = {
            "history": investment_debate_state.get("history", "") + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "bull_snapshot": new_bull_snapshot,
            "bear_snapshot": bear_snapshot,
            "debate_brief": new_debate_brief,
            "latest_speaker": "Bull Analyst",
            "judge_decision": investment_debate_state.get("judge_decision", ""),
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
