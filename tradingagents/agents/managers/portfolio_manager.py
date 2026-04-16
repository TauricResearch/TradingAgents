from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    build_optional_decision_context,
    get_language_instruction,
    summarize_structured_signal,
    truncate_prompt_text,
    use_compact_analysis_prompt,
)
from tradingagents.agents.utils.decision_utils import build_structured_decision


def create_portfolio_manager(llm, memory):
    def portfolio_manager_node(state) -> dict:

        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]
        research_structured = state.get("investment_plan_structured") or {}
        trader_structured = state.get("trader_investment_plan_structured") or {}
        portfolio_context = state.get("portfolio_context", "")
        peer_context = state.get("peer_context", "")
        decision_context = build_optional_decision_context(
            portfolio_context,
            peer_context,
            peer_context_mode=state.get("peer_context_mode", "UNSPECIFIED"),
            max_chars=550,
        )

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        if use_compact_analysis_prompt():
            prompt = f"""As the Portfolio Manager, synthesize the risk debate and deliver the final rating.

{instrument_context}

Use exactly one rating: Buy / Overweight / Hold / Underweight / Sell.
You already have enough evidence. Do not ask for more data and do not emit tool calls.

Return with this exact header first:
RATING: BUY|OVERWEIGHT|HOLD|UNDERWEIGHT|SELL
HOLD_SUBTYPE: DEFENSIVE_HOLD|STAGED_BUY_HOLD|STANDARD_HOLD|N/A
ENTRY_STYLE: IMMEDIATE|STAGED|WAIT_PULLBACK|EXISTING_ONLY|REDUCE|EXIT|UNKNOWN
SAME_THEME_RANK: LEADER|UPPER|MIDDLE|LOWER|LAGGARD|UNKNOWN
ACCOUNT_FIT: FAVORABLE|NEUTRAL|CROWDED_GROWTH|DEFENSIVE_REBALANCE|UNKNOWN

Then return only:
1. Executive summary
2. Key risks

Research plan: {truncate_prompt_text(research_plan, 500)}
Research signal summary: {summarize_structured_signal(research_structured)}
Trader plan: {truncate_prompt_text(trader_plan, 500)}
Trader signal summary: {summarize_structured_signal(trader_structured)}
Past lessons: {truncate_prompt_text(past_memory_str, 400)}
{decision_context}
Risk debate: {truncate_prompt_text(history, 1400)}{get_language_instruction()}"""
        else:
            prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Research Manager structured signal: **{summarize_structured_signal(research_structured)}**
- Trader's transaction proposal: **{trader_plan}**
- Trader structured signal: **{summarize_structured_signal(trader_structured)}**
- Lessons from past decisions: **{past_memory_str}**
{decision_context}

**Required Output Structure:**
1. Start with these exact header lines:
   - `RATING: BUY|OVERWEIGHT|HOLD|UNDERWEIGHT|SELL`
   - `HOLD_SUBTYPE: DEFENSIVE_HOLD|STAGED_BUY_HOLD|STANDARD_HOLD|N/A`
   - `ENTRY_STYLE: IMMEDIATE|STAGED|WAIT_PULLBACK|EXISTING_ONLY|REDUCE|EXIT|UNKNOWN`
   - `SAME_THEME_RANK: LEADER|UPPER|MIDDLE|LOWER|LAGGARD|UNKNOWN`
   - `ACCOUNT_FIT: FAVORABLE|NEUTRAL|CROWDED_GROWTH|DEFENSIVE_REBALANCE|UNKNOWN`
2. **Executive Summary**: A concise action plan covering entry strategy, position sizing, key risk levels, and time horizon.
3. **Investment Thesis**: Detailed reasoning anchored in the analysts' debate and past reflections.

---

**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts.
Do not ask for more data and do not emit tool calls.{get_language_instruction()}"""

        response = llm.invoke(prompt)
        structured_decision = build_structured_decision(
            response.content,
            fallback_candidates=(
                ("trader_plan", trader_plan),
                ("investment_plan", research_plan),
            ),
            default_rating="HOLD",
            peer_context_mode=state.get("peer_context_mode", "UNSPECIFIED"),
            context_usage={
                "portfolio_context": bool(str(portfolio_context).strip()),
                "peer_context": bool(str(peer_context).strip()),
            },
        )

        new_risk_debate_state = {
            "judge_decision": structured_decision["report_text"],
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
            "final_trade_decision": structured_decision["rating"],
            "final_trade_decision_report": structured_decision["report_text"],
            "final_trade_decision_structured": structured_decision,
        }

    return portfolio_manager_node
