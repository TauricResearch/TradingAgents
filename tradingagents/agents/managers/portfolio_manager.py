"""Portfolio Manager — emits the final ``MarketDecision`` for a Kalshi contract.

Re-uses the structured-output scaffolding (``with_structured_output`` + a
free-text fallback) but the schema is now ``MarketDecision`` (probability,
edge, side, Kelly stake) rather than the equity-era ``PortfolioDecision``.
The render helper produces the same ``**Rating**: ...`` markdown the
memory log and signal_processor already parse, so downstream wiring keeps
working without modification.
"""

from __future__ import annotations

from tradingagents.agents.schemas import MarketDecision, render_market_decision
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.dataflows.kalshi_market import get_market_p_yes


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, MarketDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        contract_id = state["company_of_interest"]
        instrument_context = build_instrument_context(contract_id)

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

        # Pull the latest Kalshi-implied YES probability so the PM has a
        # concrete anchor for ``market_p_yes``. When credentials are missing
        # the helper returns None; the model is instructed to emit its best
        # estimate in that case and flag the unknown in key_risks.
        market_p_yes = get_market_p_yes(contract_id)
        market_p_yes_line = (
            f"- Current Kalshi-implied YES probability (mid): {market_p_yes:.4f}\n"
            if market_p_yes is not None
            else "- Current Kalshi-implied YES probability is unavailable; "
            "infer from the analyst reports and flag the missing live quote in key_risks.\n"
        )

        prompt = f"""As the Portfolio Manager on a Kalshi prediction-market desk, synthesize the risk analysts' debate into a final, structured ``MarketDecision`` for `{contract_id}`.

{instrument_context}

---

**Output requirements (the schema enforces these):**
- ``p_yes``: your committee's probability that YES resolves true, in [0, 1].
- ``market_p_yes``: the Kalshi YES bid/ask midpoint at decision time.
- ``edge_bps``: signed edge in basis points: (p_yes - market_p_yes) × 10000.
- ``recommended_side``: YES, NO, or PASS. Use PASS when |edge_bps| is too small to justify the risk for the chosen confidence band.
- ``confidence``: low / medium / high. Reserve high for cases where multiple analyst signals converged tightly.
- ``kelly_fraction``: fractional-Kelly stake size in [0, 1]. Use a 0.25× full-Kelly multiplier as the default, scale by confidence. PASS emits 0.0.
- ``executive_summary`` / ``investment_thesis`` / ``key_risks``: prose justification, anchored in specific evidence from the analyst reports.

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{market_p_yes_line}{lessons_line}

**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence. Your edge over the Kalshi retail population is institutional-grade synthesis — exploit it.{get_language_instruction()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_market_decision,
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
