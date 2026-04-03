import time
import json

from tradingagents.agents.utils.agent_utils import (
    build_debate_brief,
    build_instrument_context,
    extract_feedback_snapshot,
    get_language_instruction,
    get_snapshot_template,
    get_snapshot_writing_instruction,
    localize_label,
    localize_rating_term,
    localize_role_name,
    truncate_for_prompt,
)


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        market_research_report = truncate_for_prompt(state["market_report"])
        sentiment_report = truncate_for_prompt(state["sentiment_report"])
        news_report = truncate_for_prompt(state["news_report"])
        fundamentals_report = truncate_for_prompt(state["fundamentals_report"])

        investment_debate_state = state["investment_debate_state"]
        bull_snapshot = investment_debate_state.get("bull_snapshot", "")
        bear_snapshot = investment_debate_state.get("bear_snapshot", "")
        debate_brief = investment_debate_state.get("debate_brief", "")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""As the portfolio manager and debate facilitator, your role is to critically evaluate this round of debate and make a definitive decision: align with the {localize_role_name("Bear Analyst")}, the {localize_role_name("Bull Analyst")}, or choose {localize_rating_term("Hold")} only if it is strongly justified based on the arguments presented.

Summarize the key points from both sides concisely, focusing on the most compelling evidence or reasoning. Your recommendation—{localize_rating_term("Buy")}, {localize_rating_term("Sell")}, or {localize_rating_term("Hold")}—must be clear and actionable. Avoid defaulting to {localize_rating_term("Hold")} simply because both sides have valid points; commit to a stance grounded in the debate's strongest arguments.

Additionally, develop a detailed investment plan for the trader. This should include:

Your Recommendation: A decisive stance supported by the most convincing arguments.
Rationale: An explanation of why these arguments lead to your conclusion.
Strategic Actions: Concrete steps for implementing the recommendation.
Take into account your past mistakes on similar situations. Use these insights to refine your decision-making and ensure you are learning and improving. Present your analysis conversationally, as if speaking naturally, without special formatting. 
After your analysis, append a feedback block in this exact format:
{get_snapshot_template()}
{get_snapshot_writing_instruction()}

Here are your past reflections on mistakes:
\"{past_memory_str}\"

{instrument_context}

Here is the latest debate context:
{localize_label("Rolling debate brief:", "滚动辩论摘要:")}
{debate_brief}

{localize_label("Bull latest snapshot:", f"{localize_role_name('Bull Analyst')} 最新快照:")}
{bull_snapshot}

{localize_label("Bear latest snapshot:", f"{localize_role_name('Bear Analyst')} 最新快照:")}
{bear_snapshot}{get_language_instruction()}
"""
        response = llm.invoke(prompt)
        judge_snapshot = extract_feedback_snapshot(response.content)
        updated_brief = build_debate_brief(
            {
                "Bull Analyst": bull_snapshot,
                "Bear Analyst": bear_snapshot,
                "Research Manager": judge_snapshot,
            },
            latest_speaker="Research Manager",
        )

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "bull_snapshot": bull_snapshot,
            "bear_snapshot": bear_snapshot,
            "debate_brief": updated_brief,
            "latest_speaker": "Research Manager",
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
