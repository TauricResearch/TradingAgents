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
from tradingagents.agents.claims import build_claim_graph
from tradingagents.agents.source_registry import build_source_registry
from tradingagents.agents.skills import build_skill_registry
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    build_scope_guard,
    get_language_instruction,
)
from tradingagents.agents.utils.recommendation_audit import (
    build_pre_synthesis_scope_audit,
    build_raw_tool_source_objects,
    build_recommendation_scorecard,
    build_source_objects,
    render_raw_tool_sources_for_prompt,
    render_scorecard_for_prompt,
    render_scope_audit_for_prompt,
    render_sources_for_prompt,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        scope_guard = build_scope_guard(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]
        audit_state = {
            "market_report": state.get("market_report", ""),
            "news_report": state.get("news_report", ""),
            "sentiment_report": state.get("sentiment_report", ""),
            "fundamentals_report": state.get("fundamentals_report", ""),
            "risk_debate_state": risk_debate_state,
            "raw_tool_outputs": state.get("raw_tool_outputs", []),
            "macro_report": state.get("macro_report", ""),
            "target_profile": state.get("target_profile", {}),
        }
        source_objects = build_source_objects(audit_state)
        raw_tool_sources = build_raw_tool_source_objects(audit_state)
        source_registry = build_source_registry(audit_state, extra_sources=source_objects + raw_tool_sources)
        claim_graph = build_claim_graph(audit_state, source_registry)
        skill_registry = build_skill_registry(audit_state, source_registry, claim_graph)
        recommendation_scorecard = build_recommendation_scorecard(audit_state)
        pre_synthesis_scope_audit = build_pre_synthesis_scope_audit(
            state["company_of_interest"],
            audit_state,
        )

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}
{scope_guard}

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
**Risk Analysts Debate History:**
{history}

**Structured Source Objects:**
Use these source IDs exactly when making material claims. Cite them inline, for example [SRC-MARKET-1].
{render_sources_for_prompt(source_objects)}

**Source Registry:**
The registry normalizes all citeable sources, including raw tool evidence and claim-linked sources.
{source_registry}

**Claim Graph:**
Use only claims that carry source IDs and explicit rationales.
{claim_graph}

**Skill Registry:**
These are the structured analyst skills available to the synthesis step.
{skill_registry}

**Raw Tool Output Sources:**
These are the raw captured tool outputs behind analyst reports. Cite relevant raw IDs inline, for example [RAW-TOOL-0001], when relying on prices, indicators, news, fundamentals, or other tool-derived evidence.
{render_raw_tool_sources_for_prompt(raw_tool_sources)}

**Pre-Synthesis Ticker/Entity Scope Audit:**
This deterministic audit is run before your final synthesis. Do not use any source flagged as out-of-scope.
{render_scope_audit_for_prompt(pre_synthesis_scope_audit)}

**Deterministic Audit Scorecard:**
This scorecard is an audit scaffold, not an instruction to trade. Reconcile your final rating against it.
{render_scorecard_for_prompt(recommendation_scorecard)}

---

Be decisive and ground every conclusion in specific evidence from the analysts.
Every material claim must cite at least one structured source ID.
When raw tool output sources are available, cite at least one RAW-TOOL source ID in the final decision.
If your final rating or directional posture differs from the deterministic audit scorecard, explicitly explain why using the word "scorecard" in that reconciliation.
If the target profile is present, explain why this recommendation fits that investor, horizon, benchmark, and risk appetite.
{get_language_instruction()}"""

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
            "source_objects": source_objects + raw_tool_sources,
            "source_registry": source_registry,
            "claim_graph": claim_graph,
            "skill_registry": skill_registry,
            "recommendation_scorecard": recommendation_scorecard,
            "pre_synthesis_scope_audit": pre_synthesis_scope_audit,
        }

    return portfolio_manager_node
