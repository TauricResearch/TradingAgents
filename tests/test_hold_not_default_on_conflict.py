"""The debate managers must not treat conflict itself as grounds for Hold (#1321).

`a4acd8a` (#1196) added "materially conflicting" to the Hold condition in both
manager prompts and both structured rating fields. But the pipeline *is* an
adversarial debate — Bull vs Bear, Aggressive vs Conservative — so material
conflict is present on every run, and the condition fired on every run. One
deployment measured 110 analyses with zero Buy/Overweight and 86-89% Hold, and
a paired A/B over 13 ticker/date cells went from 11/13 Hold back to 1/13 once
the clause was narrowed (sign test p=0.0020).

The intent of #1196 is right — do not force a direction under ambiguity. The
fix is to stop naming conflict itself as a Hold trigger, and say why: resolving
the conflict is the job.

These tests pin the wording at all four sites so a future prompt edit cannot
silently reintroduce the clause.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager

# The clause that swallowed every directional call. Must not come back.
_REGRESSION_CLAUSE = "materially conflicting"

# The replacement framing: an adversarial debate is the expected input, not a
# reason to abstain.
_ADVERSARIAL_FRAMING = "adversarial by construction"

_RISK_STATE = {
    "history": "h",
    "aggressive_history": "a",
    "conservative_history": "c",
    "neutral_history": "n",
    "current_aggressive_response": "",
    "current_conservative_response": "",
    "current_neutral_response": "",
    "latest_speaker": "Neutral",
    "count": 1,
}


def _capturing_llm(captured: dict, result):
    """LLM whose structured binding records the prompt it was handed."""
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or result
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def _prompt_text(prompt) -> str:
    """Flatten a captured prompt (str, message list, or objects) to text."""
    if isinstance(prompt, str):
        return prompt
    parts = []
    for m in prompt:
        parts.append(
            m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
        )
    return "\n".join(str(p) for p in parts)


@pytest.mark.unit
def test_research_manager_prompt_drops_the_conflict_clause():
    from tradingagents.agents.schemas import PortfolioRating, ResearchPlan

    captured = {}
    llm = _capturing_llm(
        captured,
        ResearchPlan(
            recommendation=PortfolioRating.BUY, rationale="x", strategic_actions="y"
        ),
    )
    create_research_manager(llm)({
        "company_of_interest": "NVDA",
        "investment_debate_state": {
            "history": "h", "bull_history": "b", "bear_history": "r",
            "current_response": "", "judge_decision": "", "count": 1,
        },
    })
    text = _prompt_text(captured["prompt"])
    assert _REGRESSION_CLAUSE not in text
    assert _ADVERSARIAL_FRAMING in text


@pytest.mark.unit
def test_portfolio_manager_prompt_drops_the_conflict_clause():
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating

    captured = {}
    llm = _capturing_llm(
        captured,
        PortfolioDecision(
            rating=PortfolioRating.HOLD,
            executive_summary="x",
            investment_thesis="y",
        ),
    )
    create_portfolio_manager(llm)({
        "company_of_interest": "NVDA",
        "risk_debate_state": _RISK_STATE,
        "investment_plan": "plan",
        "trader_investment_plan": "trader plan",
    })
    text = _prompt_text(captured["prompt"])
    assert _REGRESSION_CLAUSE not in text
    assert _ADVERSARIAL_FRAMING in text


@pytest.mark.unit
def test_structured_rating_descriptions_drop_the_conflict_clause():
    """The two schema fields are the model's output instructions — they matter
    as much as the prompt body, and #1196 changed all four sites together."""
    from tradingagents.agents.schemas import PortfolioDecision, ResearchPlan

    for model, field in ((ResearchPlan, "recommendation"), (PortfolioDecision, "rating")):
        description = model.model_fields[field].description
        assert description is not None, f"{model.__name__}.{field}"
        assert _REGRESSION_CLAUSE not in description, f"{model.__name__}.{field}"
        assert _ADVERSARIAL_FRAMING in description, f"{model.__name__}.{field}"


@pytest.mark.unit
def test_conflict_is_explicitly_negated_not_merely_unmentioned():
    """Guard the shape, not just the one string.

    Deleting the clause is not enough on its own: a model told only to "choose
    Hold when balanced" will still read an adversarial debate as ambiguity. The
    description must say outright that conflict is not a Hold trigger. The
    substring is present in both the broken and the fixed wording, so assert
    the negation that makes the difference.
    """
    from tradingagents.agents.schemas import PortfolioDecision, ResearchPlan

    for model, field in ((ResearchPlan, "recommendation"), (PortfolioDecision, "rating")):
        description = (model.model_fields[field].description or "").lower()
        assert "not grounds for hold" in description, f"{model.__name__}.{field}"
