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
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.research import (
    append_research_safety_block,
    build_research_decision_record,
    collect_evidence_context,
    parse_research_signal,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]
        evidence_context = collect_evidence_context(state)
        evidence_section = (
            f"**Analyst Evidence Ledgers (bounded excerpts):**\n{evidence_context}\n"
            if evidence_context
            else ""
        )

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

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
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
{evidence_section}
**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts.
This output is research support only. Preserve the five-tier directional rating, but separately
set Decision Status to No Trade, Data Insufficient, or Human Review Required when warranted.
Provide a forecast/holding horizon, expected return range, calibrated confidence, observable
invalidation conditions, key risks, and a compact evidence ledger. Label every ledger item as a
Sourced Fact, Model Inference, or Data Unavailable and include source/as-of time when available.
Do not propose an executable order or claim that position sizing is approved.

{NO_EXTERNAL_TOOLS}{get_language_instruction()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )

        research_result = None
        safety_policy = state.get("research_safety_policy")
        if safety_policy is not None:
            research_result = build_research_decision_record(
                state,
                final_trade_decision,
                policy=safety_policy,
            )
            final_trade_decision = append_research_safety_block(
                final_trade_decision,
                research_result,
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

        result = {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
        }
        if research_result is not None:
            result["research_result"] = research_result
            result["research_signal"] = parse_research_signal(
                final_trade_decision,
                research_result,
            )
        return result

    return portfolio_manager_node
