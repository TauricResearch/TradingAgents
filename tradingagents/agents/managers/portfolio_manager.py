"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call. Its rating is the run's
``final_rating``, and the decision is rendered to markdown as
``final_trade_decision`` for the memory log, CLI display and saved reports.
When a provider does not expose structured output, the agent falls back to
free-text generation and the rating is read from that text.
"""

from __future__ import annotations

from tradingagents.agents.context import (
    external_signal_prompt_block,
    get_instrument_context_from_state,
    get_language_instruction,
    get_portfolio_context_from_state,
)
from tradingagents.agents.rating import parse_rating
from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.structured import NO_EXTERNAL_TOOLS, bind_structured, invoke_structured


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        portfolio_context = get_portfolio_context_from_state(state)

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

{portfolio_context}

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

Ground every conclusion in specific evidence from the analysts. The risk debate always contains conflicting stances; deciding which is stronger is the job, so conflict alone is not a reason to Hold. Commit to the stronger case, sized by how decisively it wins. Choose Hold only when the evidence is still balanced after that weighing, or too thin to support a call; do not force a direction to appear decisive. Weigh the analysts on their merits, independent of speaking order.

## Output

Write these sections, in this order, starting with the rating on its own line:

- **Rating**: exactly one of Buy / Overweight / Hold / Underweight / Sell
- **Executive Summary**: the call and how to act on it
- **Investment Thesis**: the evidence that decided it, and what would change it
- **Holding Recommendation**: exactly one of Hold Overnight / Square Off Intraday / Data-Dependent
- **Holding Rationale**: why the position should or should not survive to tomorrow's open

{NO_EXTERNAL_TOOLS}{get_language_instruction()}"""

        # The typed rating is the decision; the rendered text only carries it.
        # Read back from text, a rating the thesis quotes could replace it.
        decision = invoke_structured(structured_llm, prompt, "Portfolio Manager")
        if decision is not None:
            final_trade_decision = render_pm_decision(decision)
            final_rating = decision.rating.value
        else:
            final_trade_decision = llm.invoke(prompt).content
            final_rating = parse_rating(final_trade_decision)

        new_risk_debate_state = {
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
            "final_rating": final_rating,
        }

    return portfolio_manager_node
