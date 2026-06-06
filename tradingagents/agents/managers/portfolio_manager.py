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
from tradingagents.personas.risk_weights import format_weighted_risk_debate


PORTFOLIO_MANAGER_SYSTEM_PROMPT = """As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

Be decisive and ground every conclusion in specific evidence from the analysts."""


def build_portfolio_manager_user_prompt(state: dict, persona=None) -> str:
    risk_debate_state = state["risk_debate_state"]
    history = format_weighted_risk_debate(risk_debate_state, persona)
    return stable_join_sections(
        [
            ("Instrument Context", build_instrument_context(state["company_of_interest"])),
            (
                "Research Manager Investment Plan",
                budgeted_dynamic_text(
                    state.get("investment_plan", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "research manager investment plan",
                ),
            ),
            (
                "Trader Transaction Proposal",
                budgeted_dynamic_text(
                    state.get("trader_investment_plan", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "trader transaction proposal",
                ),
            ),
            (
                "Lessons From Prior Decisions And Outcomes",
                budgeted_dynamic_text(
                    state.get("past_context", ""),
                    "prompt_cache_memory_budget_chars",
                    6000,
                    "memory lessons",
                ),
            ),
            (
                "Reusable Prior Analysis Pack",
                budgeted_dynamic_text(
                    state.get("prior_analysis_pack_context", ""),
                    "prompt_cache_prior_pack_budget_chars",
                    8000,
                    "prior analysis pack",
                ),
            ),
            (
                "Risk Analysts Debate History",
                budgeted_dynamic_text(
                    history,
                    "prompt_cache_debate_budget_chars",
                    8000,
                    "risk debate history",
                ),
            ),
            ("Current Task", "Produce the final portfolio decision."),
        ]
    )


def create_portfolio_manager(llm, persona=None):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        system_prompt = apply_fragment(
            PORTFOLIO_MANAGER_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_portfolio_manager_user_prompt(state, persona=persona)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
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
        }

    return portfolio_manager_node
