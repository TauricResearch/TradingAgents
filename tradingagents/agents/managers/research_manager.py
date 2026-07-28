"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.observability.errors import ObservationError
from tradingagents.research.delegation import (
    ResearchDelegationError,
    ResearchDelegationExecutor,
    ResearchDelegationRequest,
    build_default_report_lens_context,
    build_default_report_lens_delegation,
    render_delegation_results,
)


def create_research_manager(
    llm,
    *,
    delegation_executor: ResearchDelegationExecutor | None = None,
    use_default_report_lenses: bool = False,
):
    """Create the research judge with optional bounded read-only fan-out.

    A caller may inject a small allowlist of read-only tools.  The normal graph
    instead enables ``use_default_report_lenses``: code-owned, deterministic
    fan-out over already-published analyst reports.  It adds no recursive
    agent, arbitrary tool choice, or additional model turn.  Both paths make
    one structured decision, then append only public findings to the hand-off
    consumed by Trader and PM.
    """
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        history = state["investment_debate_state"].get("history", "")
        report_lens_context = (
            build_default_report_lens_context(state) if use_default_report_lenses else ""
        )

        investment_debate_state = state["investment_debate_state"]

        evidence_status = state.get("evidence_status", "")
        evidence_report = state.get("evidence_report", "")
        evidence_confidence_line = _extract_confidence_line(evidence_report)
        conviction_cap = _conviction_cap_for_evidence(evidence_status, evidence_confidence_line)

        delegation_instruction = ""
        if delegation_executor is not None:
            tool_names = ", ".join(delegation_executor.allowed_tool_names)
            delegation_instruction = (
                "\nYou may request up to three independent read-only evidence lookups in "
                f"delegation_tasks. The only permitted tool names are: {tool_names}. "
                "Each lookup must answer a distinct factual subquestion. Do not request "
                "delegation by a child, and never include private reasoning, prompts, or "
                "raw traces in a task.\n"
            )

        prompt = f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position

Commit to a clear stance whenever the debate's strongest arguments warrant one; reserve Hold for situations where the evidence on both sides is genuinely balanced.
{conviction_cap}

Present your verdict under your own identity as the Research Manager. Do not style yourself as a "Moderator" or address a moderator — there is no moderator role; you are the judge of this debate.

---

**Debate History:**
{history}
{report_lens_context}""" + delegation_instruction + NO_EXTERNAL_TOOLS + get_language_instruction()

        default_executor: ResearchDelegationExecutor | None = None
        default_requests: tuple[ResearchDelegationRequest, ...] = ()
        if use_default_report_lenses and delegation_executor is None:
            default_executor, default_requests = build_default_report_lens_delegation(state)

        investment_plan = _render_plan_with_delegation(
            structured_llm,
            llm,
            prompt,
            delegation_executor or default_executor,
            requests=default_requests if default_executor is not None else None,
        )

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node


def _render_plan_with_delegation(
    structured_llm,
    llm,
    prompt: str,
    delegation_executor: ResearchDelegationExecutor | None,
    *,
    requests: tuple[ResearchDelegationRequest, ...] | None = None,
) -> str:
    """Keep one LLM turn while appending only public delegated findings.

    A non-structured provider retains the established free-text fallback.
    Delegation-policy errors never fall back into another LLM turn; they simply
    leave the final plan without an untrusted subagent finding.
    """
    if structured_llm is None:
        rendered = invoke_structured_or_freetext(
            None, llm, prompt, render_research_plan, "Research Manager"
        )
        return _append_delegation_to_freetext(rendered, delegation_executor, requests)
    try:
        plan = structured_llm.invoke(prompt)
        if not isinstance(plan, ResearchPlan):
            raise ValueError("structured output did not produce ResearchPlan")
    except (ObservationError, AssertionError):
        raise
    except Exception:
        return invoke_structured_or_freetext(
            None, llm, prompt, render_research_plan, "Research Manager"
        )

    selected_requests = (
        requests if requests is not None else tuple(task.to_domain() for task in plan.delegation_tasks)
    )
    if delegation_executor is None or not selected_requests:
        return render_research_plan(plan)
    try:
        results = delegation_executor.execute(selected_requests)
    except ResearchDelegationError:
        # The manager's core judgement is still useful.  Avoid storing the
        # rejected request/error because it might contain model-private text.
        return render_research_plan(plan)
    return render_research_plan(plan, results)


def _append_delegation_to_freetext(
    rendered: str,
    delegation_executor: ResearchDelegationExecutor | None,
    requests: tuple[ResearchDelegationRequest, ...] | None,
) -> str:
    """Keep deterministic default lenses available to non-structured providers."""
    if delegation_executor is None or not requests:
        return rendered
    try:
        delegation = render_delegation_results(delegation_executor.execute(requests))
    except ResearchDelegationError:
        return rendered
    return f"{rendered}\n\n{delegation}" if delegation else rendered


def _extract_confidence_line(evidence_report: str) -> str | None:
    """Extract the 'Evidence confidence:' line from an evidence steward report."""
    if not evidence_report:
        return None
    for line in evidence_report.splitlines():
        if line.strip().startswith("Evidence confidence:"):
            return line.strip()
    return None


def _conviction_cap_for_evidence(
    evidence_status: str, confidence_line: str | None
) -> str:
    """Return a prompt fragment capping conviction when evidence is weak.

    Returns an empty string when evidence is PASS-level. Uses the existing
    rating-scale vocabulary (Buy/Sell → Overweight/Underweight) rather than
    inventing a parallel notion.
    """
    if evidence_status == "LOW_CONFIDENCE":
        detail = confidence_line or "evidence below sufficiency thresholds"
        return (
            f"\n**Evidence Confidence Cap:** {detail}. Because evidence coverage "
            "is below the sufficiency threshold, you MUST cap your rating at "
            "Overweight (bull-leaning) or Underweight (bear-leaning) — do NOT "
            "issue Buy or Sell. State explicitly in your rationale that evidence "
            "confidence is LOW and the rating is capped accordingly.\n"
        )
    return ""
