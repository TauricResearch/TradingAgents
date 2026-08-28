# Modified for A-share position management; see repository NOTICE.
"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.a_share import render_a_share_context
from tradingagents.agents.schemas import (
    PositionManagementPlan,
    ResearchPlan,
    render_position_management_plan,
    render_research_plan,
)
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")
    a_share_structured_llm = bind_structured(
        llm, PositionManagementPlan, "A-share Research Manager"
    )

    def research_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        history = state["investment_debate_state"].get("history", "")

        investment_debate_state = state["investment_debate_state"]
        is_a_share = state.get("asset_type") == "a_share"
        a_share_context = render_a_share_context(state.get("a_share_context"))

        if is_a_share:
            prompt = f"""As the A-share Research Manager, convert the debate into a position-management plan.

{instrument_context}
{a_share_context}

---

**Position actions** (use exactly one):
- **Add**: materially increase exposure
- **Slight Add**: add cautiously in stages
- **Hold**: keep the current position unchanged
- **Reduce**: trim part of the position
- **Exit**: close the position

Use valuation, trend, and current position jointly. Respect the deterministic matrix
baseline and explain any departure. Set a target portfolio weight and an executable
plan consistent with T+1, price limits, and 100-share buy lots.

---

**Debate History:**
{history}""" + get_language_instruction()
            active_structured = a_share_structured_llm
            renderer = render_position_management_plan
        else:
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

---

**Debate History:**
{history}""" + get_language_instruction()
            active_structured = structured_llm
            renderer = render_research_plan

        investment_plan = invoke_structured_or_freetext(
            active_structured,
            llm,
            prompt,
            renderer,
            "Research Manager",
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
