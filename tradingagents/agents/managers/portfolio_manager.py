"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back gracefully to free-text generation.
"""

from __future__ import annotations

from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.agent_utils import (
    external_signal_prompt_block,
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )
        # TradingAgents#30: state the upstream signal and make contradicting
        # it (or abstaining) something the PM has to argue for explicitly in
        # external_signal_disagreement_reason, not something that happens by
        # omission because no agent upstream carried it through.
        external_block = external_signal_prompt_block(state, require_justification=True)
        external_section = (
            f"\n{external_block}\nIf your rating disagrees with that direction or is Hold, fill "
            f"`external_signal_disagreement_reason` with the specific overriding evidence; leave it null if you agree.\n"
            if external_block else ""
        )

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

There is no existing position. Every decision here is a fresh entry, typically an options position opened today and closed at or shortly after tomorrow's open — the strategy's edge is specifically the close-to-open gap, not a multi-day directional hold. Do not phrase the executive summary or thesis in terms of trimming, adding to, or exiting a prior holding, and do not anchor on a catalyst weeks or months out (e.g. next quarter's earnings) as if it were the reason to act today, unless today's specific event is itself plausibly enough to move the instrument by tomorrow's open.

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to open a fresh long entry now
- **Overweight**: Favorable outlook; a fresh long entry is worth taking, though conviction is not maximal
- **Hold**: No new position warranted either way
- **Underweight**: Cautious/bearish; a fresh short entry is worth taking, though conviction is not maximal
- **Sell**: Strong conviction to open a fresh short entry now (or avoid any long entry)

**Holding Recommendation** (use exactly one, independent of the rating above):
- **Hold Overnight**: this is the ONLY option under which the position survives past today's close and can actually be open at tomorrow's open. If the thesis is that today's event moves the price by tomorrow's open — the strategy's core edge, and the normal case whenever the rating is driven by a same-day trigger — you MUST pick Hold Overnight, or the position gets force-closed by 15:15 TODAY and never sees the move it was opened for. Do not pick this only when the setup is multi-day; pick it whenever the payoff you're describing happens at or after tomorrow's open.
- **Square Off Intraday**: the payoff already happened DURING today's session (the gap or move you're trading already occurred intraday, before this decision), so there's nothing left to hold for overnight — the position should never survive to see tomorrow at all. This is a narrow case, not the default for a same-day-catalyst thesis.
- **Data-Dependent**: no realistic scenario resolves the thesis one way by tomorrow's open, and the honest answer is genuinely conditional in a way neither of the above captures — this behaves as a conservative Square Off Intraday downstream (same 15:15 today force-close, no overnight exposure), so only use it when that fallback is actually correct, not as a hedge to avoid committing.

Before finalizing, check your own `Time Horizon` and `Executive Summary` text: if either describes the position closing "at" or "after" tomorrow's open, `holding_recommendation` must be Hold Overnight — any other value directly contradicts what you just wrote, since the position will not exist by then otherwise.

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}{external_section}
**Risk Analysts Debate History:**
{history}

---

Ground every conclusion in specific evidence from the analysts. Commit to a directional call only when the evidence clearly supports one; choose Hold when the case is balanced, materially conflicting, ambiguous, or insufficient to justify changing exposure, rather than forcing a direction to appear decisive. Weigh the analysts on their merits, independent of speaking order.

{NO_EXTERNAL_TOOLS}{get_language_instruction()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
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
            "final_trade_decision": final_trade_decision,
        }

    return portfolio_manager_node
