import pytest

from tradingagents.portfolio import (
    PortfolioContext,
    PortfolioLimits,
    Position,
    clamp_execution,
    compute_allowed_actions,
)


def _action(actions, name):
    return next(action for action in actions if action.action == name)


def test_missing_portfolio_fails_closed_to_hold_only():
    actions = compute_allowed_actions(None, "600000.SH", 10.0)

    assert len(actions) == 1
    assert actions[0].action == "hold"
    assert actions[0].reason == "portfolio_not_provided"


def test_a_share_buy_is_limited_by_cash_fee_lot_and_position_weight():
    context = PortfolioContext(
        cash=10_000,
        mark_prices={"600000.SH": 10},
        limits=PortfolioLimits(
            max_position_weight=0.20,
            lot_size=100,
            fee_rate=0.001,
            minimum_fee=5,
        ),
    )

    actions = compute_allowed_actions(context, "600000.SH", 10)

    assert _action(actions, "buy").max_quantity == 200
    assert _action(actions, "hold").max_quantity == 0


def test_sell_cannot_exceed_current_sellable_position():
    context = PortfolioContext(
        cash=1_000,
        positions=(Position("600000.SH", quantity=500, sellable_quantity=350, average_cost=9),),
        mark_prices={"600000.SH": 10},
        limits=PortfolioLimits(lot_size=100),
    )

    assert _action(compute_allowed_actions(context, "600000.SH", 10), "sell").max_quantity == 300


def test_missing_mark_for_another_holding_fails_closed():
    context = PortfolioContext(
        cash=1_000,
        positions=(Position("000001.SZ", quantity=100, average_cost=10),),
        mark_prices={"600000.SH": 10},
    )

    with pytest.raises(ValueError, match="mark price is required"):
        compute_allowed_actions(context, "600000.SH", 10)


def test_invalid_llm_execution_is_clamped_and_audited():
    actions = compute_allowed_actions(
        PortfolioContext(cash=1_000, mark_prices={"BTC-USD": 100}),
        "BTC-USD",
        100,
    )

    action, quantity, event = clamp_execution("sell", 999, actions)

    assert (action, quantity) == ("hold", 0)
    assert event is not None
    assert event.reason == "requested_action_not_allowed"
