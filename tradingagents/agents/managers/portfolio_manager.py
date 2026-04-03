from tradingagents.agents.utils.agent_utils import (
    build_debate_brief,
    build_instrument_context,
    extract_feedback_snapshot,
    get_language_instruction,
    get_localized_final_proposal_instruction,
    get_localized_rating_scale,
    get_snapshot_template,
    get_snapshot_writing_instruction,
    localize_label,
    localize_rating_term,
    localize_role_name,
    truncate_for_prompt,
)


def create_portfolio_manager(llm, memory):
    def portfolio_manager_node(state) -> dict:

        instrument_context = build_instrument_context(state["company_of_interest"])
        risk_debate_state = state["risk_debate_state"]
        market_research_report = truncate_for_prompt(state["market_report"])
        news_report = truncate_for_prompt(state["news_report"])
        fundamentals_report = truncate_for_prompt(state["fundamentals_report"])
        sentiment_report = truncate_for_prompt(state["sentiment_report"])
        trader_plan = truncate_for_prompt(state["investment_plan"])
        aggressive_snapshot = risk_debate_state.get("aggressive_snapshot", "")
        conservative_snapshot = risk_debate_state.get("conservative_snapshot", "")
        neutral_snapshot = risk_debate_state.get("neutral_snapshot", "")
        debate_brief = risk_debate_state.get("debate_brief", "")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

---

{get_localized_rating_scale()}

**Context:**
- Trader's proposed plan: **{trader_plan}**
- Lessons from past decisions: **{past_memory_str}**

**Required Output Structure:**
1. **{localize_label("Rating", "评级")}**: State one of {localize_rating_term("Buy")} / {localize_rating_term("Overweight")} / {localize_rating_term("Hold")} / {localize_rating_term("Underweight")} / {localize_rating_term("Sell")}.
2. **{localize_label("Executive Summary", "执行摘要")}**: A concise action plan covering entry strategy, position sizing, key risk levels, and time horizon.
3. **{localize_label("Investment Thesis", "投资逻辑")}**: Detailed reasoning anchored in the analysts' debate and past reflections.

---

**{localize_label("Rolling Risk Debate Brief", "滚动风险辩论摘要")}:**
{debate_brief}

**{localize_label("Aggressive Snapshot", f"{localize_role_name('Aggressive Analyst')} 最新快照")}:**
{aggressive_snapshot}

**{localize_label("Conservative Snapshot", f"{localize_role_name('Conservative Analyst')} 最新快照")}:**
{conservative_snapshot}

**{localize_label("Neutral Snapshot", f"{localize_role_name('Neutral Analyst')} 最新快照")}:**
{neutral_snapshot}

---

Be decisive and ground every conclusion in specific evidence from the analysts. {get_localized_final_proposal_instruction()}
Append a feedback block in this exact format:
{get_snapshot_template()}
{get_snapshot_writing_instruction()}{get_language_instruction()}"""

        response = llm.invoke(prompt)
        judge_snapshot = extract_feedback_snapshot(response.content)
        updated_brief = build_debate_brief(
            {
                "Aggressive Analyst": aggressive_snapshot,
                "Conservative Analyst": conservative_snapshot,
                "Neutral Analyst": neutral_snapshot,
                "Portfolio Manager": judge_snapshot,
            },
            latest_speaker="Portfolio Manager",
        )

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "debate_brief": updated_brief,
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "aggressive_snapshot": aggressive_snapshot,
            "conservative_snapshot": conservative_snapshot,
            "neutral_snapshot": neutral_snapshot,
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return portfolio_manager_node
