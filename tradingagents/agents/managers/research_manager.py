"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.schemas import ResearchPlan, render_research_plan
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


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        history = state["investment_debate_state"].get("history", "")

        investment_debate_state = state["investment_debate_state"]
        # TradingAgents#30: the debate is where the upstream direction was
        # getting lost -- restate it to the facilitator so "balanced -> Hold"
        # is weighed against a stated prior rather than a blank.
        external_block = external_signal_prompt_block(state, require_justification=True)
        external_section = f"\n{external_block}\n" if external_block else ""

        prompt = f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.

{instrument_context}

There is no existing position to manage. Every decision here is a fresh entry, typically an options position opened today and closed at or shortly after tomorrow's open — the question is whether the event/setup under debate moves the instrument enough, soon enough, to justify opening that position now. Do not reason about trimming, adding to, or exiting a prior holding. Anchor the thesis on the catalyst that resolves within this decision's own short holding window, not on a multi-week or next-quarter event, unless that later event is itself the reason to expect a move in the next session.

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; the case for a fresh long entry now is clear
- **Overweight**: Constructive bull lean; a fresh long entry is worth taking, though conviction is not maximal
- **Hold**: Balanced or insufficient evidence; no new position is warranted either way
- **Underweight**: Cautious bear lean; a fresh short entry is worth taking, though conviction is not maximal
- **Sell**: Strong conviction in the bear thesis; the case for a fresh short entry now is clear

Commit to a directional stance only when the debate's strongest arguments clearly warrant one. Choose Hold when the evidence is balanced, materially conflicting, ambiguous, or insufficient to justify changing exposure; do not manufacture a direction merely to appear decisive. Weigh the bull and bear cases on their merits, independent of which side spoke first or last.
{external_section}
---

**Debate History:**
{history}

{NO_EXTERNAL_TOOLS}""" + get_language_instruction()

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
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
