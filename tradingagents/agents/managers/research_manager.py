"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.prompt_cache import (
    budgeted_dynamic_text,
    stable_join_sections,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.personas.prompt_overlay import apply_fragment


RESEARCH_MANAGER_SYSTEM_PROMPT = """As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position

Commit to a clear stance whenever the debate's strongest arguments warrant one; reserve Hold for situations where the evidence on both sides is genuinely balanced."""


def build_research_manager_user_prompt(state: dict) -> str:
    history = state["investment_debate_state"].get("history", "")
    prior_pack = state.get("prior_analysis_pack_context", "")
    return stable_join_sections(
        [
            ("Instrument Context", build_instrument_context(state["company_of_interest"])),
            (
                "Debate History",
                budgeted_dynamic_text(
                    history,
                    "prompt_cache_debate_budget_chars",
                    8000,
                    "investment debate history",
                ),
            ),
            (
                "Reusable Prior Analysis Pack",
                budgeted_dynamic_text(
                    prior_pack,
                    "prompt_cache_prior_pack_budget_chars",
                    8000,
                    "prior analysis pack",
                ),
            ),
            ("Current Task", "Produce the structured investment plan."),
        ]
    )


def create_research_manager(llm, persona=None):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]

        system_prompt = apply_fragment(
            RESEARCH_MANAGER_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_research_manager_user_prompt(state)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
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
