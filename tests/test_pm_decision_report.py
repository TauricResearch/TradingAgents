"""The Portfolio Manager's report contract (#1102).

``price_target`` and ``time_horizon`` are optional, and the renderer used to
drop their lines entirely when the model left them unset. A reader could not
tell "no defensible target" from "this report never carries one", and anything
reading the decision had no stable section to look for.

The fix keeps the fields optional — a forced numeric target pushes a model into
inventing precision — while making the *lines* unconditional, and asks the
model in both the prompt and the field description to give a best-effort level
whenever the analysis supports one.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.schemas import (
    NOT_PROVIDED,
    PortfolioDecision,
    PortfolioRating,
    render_pm_decision,
)

_RISK_STATE = {
    "history": "h", "aggressive_history": "a", "conservative_history": "c",
    "neutral_history": "n", "current_aggressive_response": "",
    "current_conservative_response": "", "current_neutral_response": "",
    "latest_speaker": "Neutral", "count": 1,
}

_PM_STATE = {
    "company_of_interest": "NVDA",
    "risk_debate_state": _RISK_STATE,
    "investment_plan": "plan",
    "trader_investment_plan": "trader plan",
}


def _decision(**overrides) -> PortfolioDecision:
    fields = {
        "rating": PortfolioRating.HOLD,
        "executive_summary": "Hold the position; revisit after the print.",
        "investment_thesis": "The bull and bear cases offset.",
    }
    fields.update(overrides)
    return PortfolioDecision(**fields)


@pytest.mark.unit
class TestReportSectionsAreStable:
    def test_both_optional_lines_render_when_unset(self):
        md = render_pm_decision(_decision())

        assert f"**Price Target**: {NOT_PROVIDED}" in md
        assert f"**Time Horizon**: {NOT_PROVIDED}" in md

    def test_values_render_when_set(self):
        md = render_pm_decision(_decision(price_target=215.5, time_horizon="3-6 months"))

        assert "**Price Target**: 215.5" in md
        assert "**Time Horizon**: 3-6 months" in md
        assert NOT_PROVIDED not in md

    def test_every_section_is_present_for_every_rating(self):
        """A consumer can read the same sections off any decision."""
        for rating in PortfolioRating:
            md = render_pm_decision(_decision(rating=rating))
            for header in (
                "**Rating**:",
                "**Executive Summary**:",
                "**Investment Thesis**:",
                "**Price Target**:",
                "**Time Horizon**:",
            ):
                assert header in md, f"{header} missing for {rating.value}"

    def test_a_missing_target_is_distinguishable_from_a_present_one(self):
        absent = render_pm_decision(_decision())
        present = render_pm_decision(_decision(price_target=215.5))

        assert absent.count("**Price Target**:") == 1
        assert present.count("**Price Target**:") == 1
        # The whole point: the line is always there, and says which case it is.
        assert f"**Price Target**: {NOT_PROVIDED}" in absent
        assert "**Price Target**: 215.5" in present

    def test_a_zero_target_is_not_treated_as_absent(self):
        """0.0 is falsy; it must not be reported as an unset field."""
        md = render_pm_decision(_decision(price_target=0.0))

        assert "**Price Target**: 0.0" in md
        assert f"**Price Target**: {NOT_PROVIDED}" not in md


@pytest.mark.unit
class TestTheModelIsAskedForATarget:
    def test_field_description_rules_out_percentages_and_ranges(self):
        """The description is what the model is handed as its instruction."""
        description = PortfolioDecision.model_fields["price_target"].description

        assert "never a percentage" in description
        assert "never a range" in description
        assert "midpoint" in description

    def test_prompt_asks_for_a_best_effort_level(self):
        captured = {}
        structured = MagicMock()
        structured.invoke.side_effect = lambda prompt: (
            captured.__setitem__("prompt", prompt) or _decision()
        )
        llm = MagicMock()
        llm.with_structured_output.return_value = structured

        create_portfolio_manager(llm)(dict(_PM_STATE))

        prompt = captured["prompt"]
        prompt = prompt if isinstance(prompt, str) else str(prompt)
        assert "price target" in prompt.lower()
        # A Hold is the case the issue reported as silently target-less.
        assert "Hold does not excuse" in prompt

    def test_node_output_carries_the_line(self):
        """End to end: what lands in final_trade_decision, not just the renderer."""
        structured = MagicMock()
        structured.invoke.return_value = _decision()
        llm = MagicMock()
        llm.with_structured_output.return_value = structured

        result = create_portfolio_manager(llm)(dict(_PM_STATE))

        assert f"**Price Target**: {NOT_PROVIDED}" in result["final_trade_decision"]
        assert result["risk_debate_state"]["judge_decision"] == result["final_trade_decision"]
