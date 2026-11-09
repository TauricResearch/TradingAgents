"""Trade actions (§6): a rating is not an order.

The 19:24 report proposed SELL at 573.10, stop 546, "reduce exposure 30-40%".
None of that is executable against an unknown book — selling 40% of nothing is
not a trade, and a SELL rating on a flat account is not a short.

These tests pin the distinction the task requires: a strategic rating says
what the analyst thinks, a ``TradeAction`` says what to do to the book, and
deriving one from the other silently is the defect.
"""

from __future__ import annotations

import pytest

from tradingagents.dataflows.math.trade_actions import (
    PositionState,
    TradeAction,
    actions_for_rating,
    resolve_trade_intent,
    validate_trade_against_rating,
)

HELD = PositionState(known=True, quantity=10.0, average_price=570.0)
FLAT = PositionState(known=True, quantity=0.0)
SHORT = PositionState(known=True, quantity=-8.0, average_price=580.0)
UNKNOWN = PositionState(known=False)


class TestRatingIsNotAnAction:
    def test_sell_is_not_a_tradeable_rating(self):
        """§6: 'SELL' names a direction, not a book operation."""
        assert actions_for_rating("SELL") == ()
        assert actions_for_rating("BUY") == ()

    def test_underweight_permits_reduction_not_shorting(self):
        permitted = actions_for_rating("UNDERWEIGHT")
        assert TradeAction.REDUCE_LONG in permitted
        assert TradeAction.CLOSE_LONG in permitted
        assert TradeAction.OPEN_SHORT not in permitted

    def test_overweight_does_not_permit_opening_a_short(self):
        permitted = actions_for_rating("OVERWEIGHT")
        assert TradeAction.OPEN_LONG in permitted
        assert TradeAction.OPEN_SHORT not in permitted

    def test_a_bare_sell_cannot_become_an_open_short(self):
        """The exact failure §6 forbids."""
        intent = validate_trade_against_rating(
            TradeAction.OPEN_SHORT, "SELL", position=FLAT)
        assert intent.blocks is True
        assert intent.reason_code == "RATING_NOT_TRADEABLE"
        assert intent.is_executable is False

    def test_an_action_outside_the_rating_is_refused(self):
        intent = validate_trade_against_rating(
            TradeAction.CLOSE_LONG, "OVERWEIGHT", position=HELD)
        assert intent.reason_code == "ACTION_NOT_PERMITTED_BY_RATING"


class TestT15ReduceLongWithAPosition:
    def test_a_valid_reduction_sells_a_fraction_of_the_held_quantity(self):
        """40% of 10 shares is 4, computed from the book — not from a guess."""
        intent = resolve_trade_intent(TradeAction.REDUCE_LONG, HELD,
                                      reduce_fraction=0.4)
        assert intent.quantity == pytest.approx(4.0)
        assert intent.is_executable is True

    def test_a_reduction_never_sells_more_than_is_held(self):
        intent = resolve_trade_intent(TradeAction.REDUCE_LONG, HELD,
                                      reduce_fraction=0.9)
        assert intent.quantity <= HELD.quantity

    def test_closing_sells_the_whole_position(self):
        intent = resolve_trade_intent(TradeAction.CLOSE_LONG, HELD)
        assert intent.quantity == pytest.approx(10.0)

    def test_a_fraction_above_one_is_refused_not_capped_silently(self):
        """A 150% reduction is a bad instruction, not a 100% one."""
        intent = resolve_trade_intent(TradeAction.REDUCE_LONG, HELD,
                                      reduce_fraction=1.5)
        assert intent.blocks is True
        assert intent.reason_code == "INVALID_REDUCTION_FRACTION"


class TestT16ReduceLongWithoutAPosition:
    def test_a_reduction_on_a_flat_book_blocks(self):
        intent = resolve_trade_intent(TradeAction.REDUCE_LONG, FLAT)
        assert intent.blocks is True
        assert intent.reason_code == "NO_LONG_POSITION"
        assert intent.is_executable is False

    def test_a_reduction_with_an_unknown_book_blocks(self):
        """An absent portfolio is not a flat one, and yields no quantity."""
        intent = resolve_trade_intent(TradeAction.REDUCE_LONG, UNKNOWN)
        assert intent.blocks is True
        assert intent.reason_code == "PORTFOLIO_UNKNOWN"
        assert intent.quantity == 0.0

    def test_closing_a_position_that_does_not_exist_blocks(self):
        intent = resolve_trade_intent(TradeAction.CLOSE_LONG, FLAT)
        assert intent.reason_code == "NO_LONG_POSITION"


class TestT17OpenShortWithAWrongSideStop:
    def test_a_short_without_authorization_blocks(self):
        intent = resolve_trade_intent(TradeAction.OPEN_SHORT, FLAT)
        assert intent.blocks is True
        assert intent.reason_code == "SHORT_NOT_AUTHORIZED"

    def test_an_authorized_short_still_needs_a_size_from_the_risk_engine(self):
        intent = resolve_trade_intent(TradeAction.OPEN_SHORT, FLAT,
                                      short_authorized=True)
        assert intent.reason_code == "SIZE_REQUIRED"
        assert intent.quantity == 0.0
        assert intent.is_executable is False

    def test_an_authorized_short_on_a_held_position_blocks(self):
        intent = resolve_trade_intent(TradeAction.OPEN_SHORT, HELD,
                                      short_authorized=True)
        assert intent.reason_code == "POSITION_ALREADY_OPEN"

    def test_a_wrong_side_stop_is_refused_by_the_stop_check(self):
        """Case T17: a SHORT stop below entry protects nothing."""
        from tradingagents.dataflows.math.consistency import check_stop_consistency

        finding = check_stop_consistency(573.10, 546.00, 9.524,
                                         direction="SHORT")
        assert finding is not None
        assert finding.code == "STOP_WRONG_SIDE"
        assert finding.blocks is True

    def test_the_reports_proposal_is_short_with_a_long_side_stop(self):
        """573.10 with a 546 stop is a LONG-shaped stop on a SELL proposal."""
        from tradingagents.dataflows.math.consistency import check_stop_consistency

        # As a LONG the stop is valid...
        assert check_stop_consistency(573.10, 546.00, 9.524,
                                      direction="LONG") is None
        # ...which is precisely why it cannot silently become a SHORT.
        assert check_stop_consistency(573.10, 546.00, 9.524,
                                      direction="SHORT") is not None


class TestShortSideReductions:
    def test_reducing_a_short_covers_part_of_it(self):
        intent = resolve_trade_intent(TradeAction.REDUCE_SHORT, SHORT,
                                      reduce_fraction=0.5,
                                      short_authorized=True)
        assert intent.quantity == pytest.approx(4.0)

    def test_closing_a_short_covers_all_of_it(self):
        intent = resolve_trade_intent(TradeAction.CLOSE_SHORT, SHORT,
                                      short_authorized=True)
        assert intent.quantity == pytest.approx(8.0)

    def test_covering_a_short_that_does_not_exist_blocks(self):
        intent = resolve_trade_intent(TradeAction.CLOSE_SHORT, FLAT,
                                      short_authorized=True)
        assert intent.reason_code == "NO_SHORT_POSITION"


class TestWaitIsAlwaysAvailable:
    def test_wait_needs_no_book(self):
        intent = resolve_trade_intent(TradeAction.WAIT, UNKNOWN)
        assert intent.blocks is False
        assert intent.is_executable is False

    def test_wait_is_permitted_by_every_rating(self):
        for rating in ("OVERWEIGHT", "NEUTRAL", "UNDERWEIGHT"):
            assert TradeAction.WAIT in actions_for_rating(rating)
