"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back gracefully to free-text generation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict

from tradingagents.agents.schemas import (
    PortfolioDecision,
    RiskDebateSignal,
    render_pm_decision,
)
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.portfolio import (
    AllowedAction,
    aggregate_risk_convictions,
    clamp_execution,
    compute_allowed_actions,
    feature_contributions_from_dicts,
    portfolio_context_from_dict,
    rank_feature_contributions,
)
from tradingagents.skills import (
    build_role_skill_prompt,
    build_skill_trigger_context,
    emit_methodology_artifact,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        risk_signals = _risk_signals_from_state(risk_debate_state)
        risk_signal_context = _render_risk_signal_context(risk_signals)
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        evidence_status = state.get("evidence_status", "")
        evidence_report = state.get("evidence_report", "")
        evidence_confidence_line = _extract_evidence_confidence_line(evidence_report)
        conviction_cap = _pm_conviction_cap_for_evidence(evidence_status, evidence_confidence_line)

        skill_trigger_text = build_skill_trigger_context(
            research_plan, trader_plan, risk_debate_state.get("history", "")
        )
        emit_methodology_artifact("portfolio_manager", trigger_text=skill_trigger_text)

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        allowed_actions, constraint_reason = _allowed_actions_from_state(state)
        constraints_line = (
            "\n**Deterministic Execution Constraints:**\n"
            + json.dumps([asdict(action) for action in allowed_actions], ensure_ascii=False)
            + "\nChoose execution_action and requested_quantity only from this set. "
            + "The system will enforce these limits after your response.\n"
        )
        if constraint_reason:
            constraints_line += f"Constraint note: {constraint_reason}\n"

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry
{conviction_cap}

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{history}

**Typed Public Risk Signals:**
{risk_signal_context}

---

Be decisive and ground every conclusion in specific evidence from the analysts.

{NO_EXTERNAL_TOOLS}{get_language_instruction()}"""

        prompt += (
            "\nThe typed public risk signals above are the only risk-conviction input. "
            "Do not recreate, reinterpret, or emit substitute risk signals from the "
            "debate prose. List up to five top_drivers only when each has a concrete report section, "
            "source URI, or artifact reference. Do not invent causal attribution.\n"
        )
        prompt += build_role_skill_prompt(
            "portfolio_manager", trigger_text=skill_trigger_text
        )
        prompt += constraints_line
        enforce_constraints = state.get("portfolio_context") is not None
        final_trade_decision, clamp_events = _constrained_pm_decision(
            structured_llm,
            llm,
            prompt,
            allowed_actions,
            enforce_constraints,
            risk_signals,
        )
        final_trade_decision = _append_measured_feature_contributions(
            final_trade_decision,
            state.get("feature_contributions"),
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
            "risk_signals": risk_debate_state.get("risk_signals", []),
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
            "allowed_actions": [asdict(action) for action in allowed_actions],
            "clamp_events": [asdict(event) for event in clamp_events],
        }

    return portfolio_manager_node


def _allowed_actions_from_state(state) -> tuple[tuple[AllowedAction, ...], str | None]:
    """Compute executable limits from user-provided facts, never from LLM prose."""
    try:
        context = portfolio_context_from_dict(state.get("portfolio_context"))
        price = context.mark_prices.get(state["company_of_interest"]) if context else None
        return compute_allowed_actions(context, state["company_of_interest"], price), None
    except (KeyError, TypeError, ValueError) as exc:
        return (AllowedAction("hold", 0, None, "portfolio_constraint_unavailable"),), str(exc)


def _constrained_pm_decision(
    structured_llm,
    llm,
    prompt,
    allowed_actions,
    enforce_constraints,
    risk_signals,
):
    """Run the PM once, then make its requested order legal deterministically."""
    if not enforce_constraints:
        return (
            invoke_structured_or_freetext(
                structured_llm,
                llm,
                prompt,
                lambda decision: render_pm_decision(decision, risk_signals=risk_signals),
                "Portfolio Manager",
            ),
            [],
        )
    if structured_llm is not None:
        try:
            decision = structured_llm.invoke(prompt)
            if not isinstance(decision, PortfolioDecision):
                raise ValueError("structured output did not produce PortfolioDecision")
            action_name = decision.execution_action.value if decision.execution_action else "hold"
            quantity = decision.requested_quantity or 0
            applied_action, applied_quantity, event = clamp_execution(
                action_name, quantity, allowed_actions
            )
            rendered = render_pm_decision(decision, risk_signals=risk_signals)
            rendered += f"\n\n**Execution Constraint**: {applied_action.upper()} {applied_quantity}"
            if event is not None:
                rendered += "\n\n**Clamp Audit**: " + json.dumps(asdict(event), ensure_ascii=False)
                return rendered, [event]
            return rendered, []
        except Exception:
            # Preserve the existing provider-agnostic fallback behavior. A
            # free-text response cannot safely request an order, so the
            # deterministic result below remains Hold.
            pass

    rendered = invoke_structured_or_freetext(
        None,
        llm,
        prompt,
        lambda decision: render_pm_decision(decision, risk_signals=risk_signals),
        "Portfolio Manager",
    )
    return rendered + "\n\n**Execution Constraint**: HOLD 0", []


def _risk_signals_from_state(risk_debate_state: Mapping[str, object]) -> list[RiskDebateSignal]:
    """Decode only independently produced risk signals; never mine debate prose."""
    raw_signals = risk_debate_state.get("risk_signals", [])
    if not isinstance(raw_signals, list):
        return []
    parsed: list[RiskDebateSignal] = []
    seen: set[str] = set()
    for raw_signal in raw_signals:
        if not isinstance(raw_signal, Mapping):
            continue
        try:
            signal = RiskDebateSignal.model_validate(raw_signal)
        except (TypeError, ValueError):
            continue
        if signal.role in seen:
            continue
        seen.add(signal.role)
        parsed.append(signal)
    return parsed


def _render_risk_signal_context(signals: list[RiskDebateSignal]) -> str:
    if not signals:
        return "No validated public risk signals are available; do not infer one from prose."
    aggregate = aggregate_risk_convictions([signal.to_domain() for signal in signals])
    conviction = "abstain" if aggregate.conviction is None else f"{aggregate.conviction:+.2f}"
    lines = [
        f"Aggregate: conviction={conviction}; disagreement={aggregate.disagreement}; "
        f"abstained={','.join(aggregate.abstained_roles) or 'none'}"
    ]
    for signal in signals:
        value = "abstain" if signal.abstain else f"{signal.conviction:+.2f}"
        lines.append(
            f"- {signal.role}: conviction={value}; confidence={signal.confidence:.2f}; "
            f"evidence={signal.evidence_summary}"
        )
    return "\n".join(lines)


def _append_measured_feature_contributions(decision: str, raw_contributions: object) -> str:
    """Append deterministic |z| × importance drivers when an upstream artifact exists."""
    try:
        contributions = rank_feature_contributions(
            feature_contributions_from_dicts(raw_contributions)
        )
    except (KeyError, TypeError, ValueError):
        return decision
    if not contributions:
        return decision
    lines = ["", "**Top Measured Feature Contributions**:"]
    lines.extend(
        f"- {item.direction}: {item.feature} "
        f"(|z|×importance={item.contribution:.3f}; evidence={item.evidence_ref}"
        + (
            f"; artifact={item.source_artifact_id}"
            if item.source_artifact_id is not None
            else ""
        )
        + ")"
        for item in contributions
    )
    return decision + "\n" + "\n".join(lines)


def _extract_evidence_confidence_line(evidence_report: str) -> str | None:
    """Extract the 'Evidence confidence:' line from an evidence steward report."""
    if not evidence_report:
        return None
    for line in evidence_report.splitlines():
        if line.strip().startswith("Evidence confidence:"):
            return line.strip()
    return None


def _pm_conviction_cap_for_evidence(
    evidence_status: str, confidence_line: str | None
) -> str:
    """Return a prompt fragment capping final-decision conviction on weak evidence.

    Mirrors the research-manager cap but speaks in the PM's vocabulary:
    final rating capped at Overweight/Underweight, and confidence in the
    typed decision must be reduced.
    """
    if evidence_status == "LOW_CONFIDENCE":
        detail = confidence_line or "evidence below sufficiency thresholds"
        return (
            f"\n**Evidence Confidence Cap:** {detail}. Because upstream evidence "
            "coverage is below the sufficiency threshold, you MUST cap your "
            "rating at Overweight (bull-leaning) or Underweight (bear-leaning) "
            "— do NOT issue Buy or Sell. Set your decision confidence to reflect "
            "the weakened evidence base, and state explicitly in your rationale "
            "that evidence confidence is LOW and the rating is capped accordingly.\n"
        )
    return ""
