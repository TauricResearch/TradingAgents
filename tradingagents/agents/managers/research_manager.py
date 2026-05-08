"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.schemas import PortfolioRating, ResearchPlan, render_research_plan
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def _extract_stance(text: str) -> str:
    """Extract the last mentioned rating stance from debate history text.

    Returns one of Buy / Overweight / Hold / Underweight / Sell / Unknown.
    """
    if not text:
        return "Unknown"
    ratings = [r.value for r in PortfolioRating]
    last_pos = -1
    last_rating = "Unknown"
    for rating in ratings:
        pos = text.rfind(rating)
        if pos > last_pos:
            last_pos = pos
            last_rating = rating
    return last_rating


def _compute_debate_metrics(debate_state: dict) -> dict:
    """Compute debate quality metrics from the investment debate state."""
    count = debate_state.get("count", 0) or 0
    rounds_executed = count // 2

    bull_stance = _extract_stance(debate_state.get("bull_history", ""))
    bear_stance = _extract_stance(debate_state.get("bear_history", ""))

    was_contested = bull_stance != bear_stance and bull_stance != "Unknown" and bear_stance != "Unknown"

    return {
        "rounds_executed": rounds_executed,
        "bull_stance": bull_stance,
        "bear_stance": bear_stance,
        "was_contested": was_contested,
        "agreement_score": "disagree" if was_contested else "agree",
    }


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["investment_debate_state"].get("history", "")

        investment_debate_state = state["investment_debate_state"]

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
{history}"""

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )

        debate_metrics = _compute_debate_metrics(investment_debate_state)

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state.get("count", 0),
            "debate_metrics": debate_metrics,
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
