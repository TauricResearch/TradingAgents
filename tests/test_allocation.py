from decimal import Decimal

import pytest

from tradingagents.allocation import (
    OrderIntent,
    conviction_targets,
    reconcile_targets,
)


def test_conviction_targets_normalize_signed_weights_with_thirty_percent_cap():
    targets = conviction_targets(
        {"AAPL": "Buy", "MSFT": "Overweight", "TSLA": "Sell", "META": "Hold"},
        cash=Decimal("10000"),
        max_cash_allocation=Decimal("0.30"),
    )
    assert targets == {
        "AAPL": Decimal("1200"),
        "MSFT": Decimal("600"),
        "TSLA": Decimal("-1200"),
        "META": Decimal("0"),
    }
    assert sum(abs(value) for value in targets.values()) == Decimal("3000")


@pytest.mark.parametrize(
    "max_cash_allocation",
    [Decimal("0"), Decimal("-0.01"), Decimal("0.3001")],
)
def test_conviction_targets_reject_invalid_cash_allocation_caps(
    max_cash_allocation,
):
    with pytest.raises(ValueError, match="max_cash_allocation"):
        conviction_targets(
            {"AAPL": "Buy"},
            cash=Decimal("1000"),
            max_cash_allocation=max_cash_allocation,
        )


def test_conviction_targets_accept_thirty_percent_cash_allocation_cap():
    assert conviction_targets(
        {"AAPL": "Buy"},
        cash=Decimal("1000"),
        max_cash_allocation=Decimal("0.30"),
    ) == {"AAPL": Decimal("300.00")}


def test_underweight_has_half_the_absolute_weight_of_buy_and_sell():
    targets = conviction_targets(
        {"AAPL": "Buy", "MSFT": "Underweight", "TSLA": "Sell"},
        cash=Decimal("1000"),
        max_cash_allocation=Decimal("0.30"),
    )

    assert targets == {
        "AAPL": Decimal("120"),
        "MSFT": Decimal("-60"),
        "TSLA": Decimal("-120"),
    }


def test_non_positive_cash_and_all_hold_produce_zero_targets():
    assert conviction_targets({"AAPL": "Buy"}, Decimal("0"), Decimal("0.30"))["AAPL"] == 0
    assert conviction_targets({"AAPL": "Hold"}, Decimal("1000"), Decimal("0.30"))["AAPL"] == 0


def test_reconciliation_includes_signed_open_order_exposure_and_threshold():
    intents = reconcile_targets(
        targets={"AAPL": Decimal("1000"), "TSLA": Decimal("-500")},
        positions={"AAPL": Decimal("600"), "TSLA": Decimal("-200")},
        open_orders={"AAPL": Decimal("100"), "TSLA": Decimal("-100")},
        threshold=Decimal("50"),
    )
    assert intents == [
        OrderIntent("AAPL", "buy", Decimal("300"), Decimal("1000")),
        OrderIntent("TSLA", "sell", Decimal("200"), Decimal("-500")),
    ]


@pytest.mark.parametrize(
    ("rating", "sign"),
    [("Buy", 1), ("Overweight", 1), ("Hold", 0), ("Underweight", -1), ("Sell", -1)],
)
def test_every_rating_has_the_expected_direction(rating, sign):
    target = conviction_targets({"AAPL": rating}, Decimal("1000"), Decimal("0.30"))["AAPL"]
    assert (target > 0) - (target < 0) == sign


def test_unknown_rating_is_rejected():
    with pytest.raises(ValueError, match="unsupported rating"):
        conviction_targets({"AAPL": "Strong Buy"}, Decimal("1000"), Decimal("0.30"))


@pytest.mark.parametrize(
    ("position", "expected_side"),
    [(Decimal("500"), "sell"), (Decimal("-500"), "buy")],
)
def test_hold_target_closes_long_or_short(position, expected_side):
    intents = reconcile_targets({"AAPL": Decimal("0")}, {"AAPL": position}, {}, Decimal("10"))
    assert intents[0].side == expected_side
    assert intents[0].notional == Decimal("500")


def test_delta_below_threshold_is_suppressed():
    assert (
        reconcile_targets({"AAPL": Decimal("100")}, {"AAPL": Decimal("95")}, {}, Decimal("10"))
        == []
    )


def test_public_boundaries_convert_floats_via_string_and_preserve_input_order():
    targets = conviction_targets(
        {"MSFT": "Overweight", "AAPL": "Buy"},
        cash=0.3,
        max_cash_allocation=0.1,
    )

    assert list(targets) == ["MSFT", "AAPL"]
    assert sum(abs(value) for value in targets.values()) == Decimal("0.03")


def test_reconciliation_preserves_target_order_and_converts_float_boundaries():
    intents = reconcile_targets(
        targets={"MSFT": 200.0, "AAPL": 100.0},
        positions={"MSFT": 50.0},
        open_orders={"AAPL": 25.0},
        threshold=10.0,
    )

    assert intents == [
        OrderIntent("MSFT", "buy", Decimal("150.0"), Decimal("200.0")),
        OrderIntent("AAPL", "buy", Decimal("75.0"), Decimal("100.0")),
    ]
