"""A decision's price levels are checked against its direction, in code (#1168).

A Buy whose stop sits above its entry is stopped out as it fills, and a Buy
rating whose target is below the price paid expects a loss. Either reads as a
normal call unless something compares the numbers, so the conflict is printed
beside the decision. The decision itself is never changed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.consistency import (
    decision_level_warnings,
    trader_entry_price,
    trader_level_warnings,
)
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    TraderAction,
    TraderProposal,
    render_trader_proposal,
)
from tradingagents.agents.trader.trader import create_trader


def _proposal(action=TraderAction.BUY, entry=100.0, stop=95.0):
    return TraderProposal(action=action, reasoning="r", entry_price=entry, stop_loss=stop)


def _decision(rating=PortfolioRating.BUY, target=120.0):
    return PortfolioDecision(
        rating=rating, executive_summary="s", investment_thesis="t", price_target=target
    )


def _structured_llm(result):
    structured = MagicMock()
    structured.invoke.return_value = result
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestTraderLevels:
    def test_a_buy_with_its_stop_below_entry_is_consistent(self):
        assert trader_level_warnings(_proposal()) == []

    @pytest.mark.parametrize("stop", [100.0, 104.0])
    def test_a_buy_with_its_stop_at_or_above_entry_is_flagged(self, stop):
        [warning] = trader_level_warnings(_proposal(stop=stop))
        assert "stop-loss" in warning and "100" in warning

    def test_a_sell_is_not_judged_by_the_side_of_its_stop(self):
        """A Sell may exit a holding, where a stop below the exit price is a plan."""
        assert trader_level_warnings(_proposal(TraderAction.SELL, stop=90.0)) == []
        assert trader_level_warnings(_proposal(TraderAction.SELL, stop=110.0)) == []

    @pytest.mark.parametrize("entry, stop", [(None, 95.0), (100.0, None), (None, None)])
    def test_a_level_not_given_is_not_a_conflict(self, entry, stop):
        assert trader_level_warnings(_proposal(entry=entry, stop=stop)) == []

    def test_a_sub_cent_buy_is_compared_as_given(self):
        assert trader_level_warnings(_proposal(entry=0.00002, stop=0.00001)) == []
        assert trader_level_warnings(_proposal(entry=0.00001, stop=0.00002))


@pytest.mark.unit
class TestTraderEntryPrice:
    def test_the_rendered_entry_is_read_back(self):
        assert trader_entry_price(render_trader_proposal(_proposal(entry=189.5))) == 189.5

    def test_a_sub_cent_entry_survives_its_rendering(self):
        """str() writes 0.00001 as 1e-05."""
        assert trader_entry_price(render_trader_proposal(_proposal(entry=0.00001))) == 0.00001

    def test_an_entry_not_provided_is_none(self):
        assert trader_entry_price(render_trader_proposal(_proposal(entry=None))) is None

    @pytest.mark.parametrize(
        "line, expected",
        [
            ("- **Entry Price**: $1,234.50", 1234.5),
            ("Entry Price: 42", 42.0),
            ("**Entry Price**: **97.1**", 97.1),
        ],
    )
    def test_a_free_text_entry_line_is_read(self, line, expected):
        assert trader_entry_price(f"**Action**: Buy\n\n{line}\n") == expected

    @pytest.mark.parametrize(
        "text",
        [
            "**Entry Price**: 180-185",
            "**Entry Price**: near support",
            "We would like an entry price: 150 or so, if the market allows.",
            "**Entry Price**: 0",
            "",
        ],
    )
    def test_anything_but_one_number_on_the_label_line_is_none(self, text):
        assert trader_entry_price(text) is None


@pytest.mark.unit
class TestDecisionLevels:
    @pytest.mark.parametrize("rating", [PortfolioRating.BUY, PortfolioRating.OVERWEIGHT])
    def test_a_long_rating_with_a_target_above_entry_is_consistent(self, rating):
        assert decision_level_warnings(_decision(rating), 100.0) == []

    @pytest.mark.parametrize("rating", [PortfolioRating.BUY, PortfolioRating.OVERWEIGHT])
    @pytest.mark.parametrize("target", [100.0, 80.0])
    def test_a_long_rating_with_a_target_at_or_below_entry_is_flagged(self, rating, target):
        [warning] = decision_level_warnings(_decision(rating, target), 100.0)
        assert rating.value in warning and "price target" in warning

    @pytest.mark.parametrize(
        "rating", [PortfolioRating.HOLD, PortfolioRating.UNDERWEIGHT, PortfolioRating.SELL]
    )
    def test_other_ratings_are_not_checked(self, rating):
        assert decision_level_warnings(_decision(rating, 80.0), 100.0) == []

    def test_without_a_target_or_an_entry_there_is_nothing_to_compare(self):
        assert decision_level_warnings(_decision(target=None), 100.0) == []
        assert decision_level_warnings(_decision(target=80.0), None) == []


@pytest.mark.unit
class TestNodes:
    def test_the_trader_prints_the_conflict_before_its_final_line(self):
        state = {"company_of_interest": "NVDA", "investment_plan": "Buy", "market_report": ""}
        plan = create_trader(_structured_llm(_proposal(stop=104.0)))(state)[
            "trader_investment_plan"
        ]
        assert "**Level Check**: The stop-loss (104)" in plan
        assert plan.rstrip().endswith("FINAL TRANSACTION PROPOSAL: **BUY**")

    def test_a_consistent_trader_plan_has_no_check_line(self):
        state = {"company_of_interest": "NVDA", "investment_plan": "Buy", "market_report": ""}
        plan = create_trader(_structured_llm(_proposal()))(state)["trader_investment_plan"]
        assert "Level Check" not in plan

    def test_the_portfolio_manager_checks_its_target_against_the_trader_entry(self):
        state = {
            "company_of_interest": "NVDA",
            "investment_plan": "Buy",
            "trader_investment_plan": render_trader_proposal(_proposal(entry=100.0)),
            "risk_debate_state": {
                "history": "",
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "count": 1,
            },
        }
        out = create_portfolio_manager(_structured_llm(_decision(target=90.0)))(state)
        assert (
            "**Level Check**: A Buy rating has a price target (90)" in out["final_trade_decision"]
        )
        # The check reports; the decision stays the model's own.
        assert out["final_rating"] == "Buy"
