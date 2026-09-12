"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
from tradingagents.dataflows import config


def build_research_manager_prompt(state: Mapping[str, Any], *, output_language: str) -> str:
    """Build the Research Manager prompt without invoking the model."""
    history = state["investment_debate_state"].get("history", "")
    return f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.

{get_instrument_context_from_state(state)}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position

Commit to a directional stance only when the debate's strongest arguments clearly warrant one. Choose Hold when the evidence is balanced, materially conflicting, ambiguous, or insufficient to justify changing exposure; do not manufacture a direction merely to appear decisive. Weigh the bull and bear cases on their merits, independent of which side spoke first or last.

---

**Debate History:**
{history}

{NO_EXTERNAL_TOOLS}""" + get_language_instruction(output_language)


def apply_research_manager_output(state: Mapping[str, Any], output: str) -> dict[str, Any]:
    investment_debate_state = state["investment_debate_state"]
    return {
        "investment_debate_state": {
            "judge_decision": output,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": output,
            "count": investment_debate_state["count"],
        },
        "investment_plan": output,
    }


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        language = config.get_config().get("output_language", "English")
        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            build_research_manager_prompt(state, output_language=language),
            render_research_plan,
            "Research Manager",
        )
        return apply_research_manager_output(state, investment_plan)

    return research_manager_node
