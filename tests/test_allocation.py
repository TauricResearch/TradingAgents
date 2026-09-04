from datetime import date, timedelta
from decimal import Decimal

import pytest

from tradingagents.allocation import (
    OrderIntent,
    conviction_targets,
    reconcile_targets,
)
from tradingagents.risk import scale_equity_targets


def test_conviction_targets_normalize_signed_weights_with_ninety_percent_cap():
    targets = conviction_targets(
        {"AAPL": "Buy", "MSFT": "Overweight", "TSLA": "Sell", "META": "Hold"},
        cash=Decimal("10000"),
        max_cash_allocation=Decimal("0.90"),
    )
    assert targets == {
        "AAPL": Decimal("3600"),
        "MSFT": Decimal("1800"),
        "TSLA": Decimal("-3600"),
        "META": Decimal("0"),
    }
    assert sum(abs(value) for value in targets.values()) == Decimal("9000")


@pytest.mark.parametrize(
    "max_cash_allocation",
    [Decimal("0"), Decimal("-0.01"), Decimal("0.9001")],
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


def test_conviction_targets_accept_ninety_percent_cash_allocation_cap():
    assert conviction_targets(
        {"AAPL": "Buy"},
        cash=Decimal("1000"),
        max_cash_allocation=Decimal("0.90"),
    ) == {"AAPL": Decimal("900.00")}


def test_cash_reserve_scales_positive_convictions_without_reversing_shorts():
    targets = conviction_targets(
        {"AAPL": "Buy", "MSFT": "Overweight", "TSLA": "Sell"},
        cash=Decimal("800"),
        max_cash_allocation=Decimal("0.90"),
        equity=Decimal("1000"),
        max_cash_reserve=Decimal("70"),
    )

    assert targets == {
        "AAPL": Decimal("812"),
        "MSFT": Decimal("406"),
        "TSLA": Decimal("-288"),
    }
    assert Decimal("1000") - sum(targets.values()) == Decimal("70")


def test_cash_reserve_does_not_reduce_buy_only_baseline_when_ceiling_is_met():
    targets = conviction_targets(
        {"AAPL": "Buy"},
        cash=Decimal("50000"),
        max_cash_allocation=Decimal("0.90"),
        equity=Decimal("100000"),
        max_cash_reserve=Decimal("70000"),
    )

    assert targets == {"AAPL": Decimal("45000.00")}


def test_cash_reserve_does_not_reduce_balanced_baseline_when_ceiling_is_met():
    targets = conviction_targets(
        {"AAPL": "Buy", "TSLA": "Sell"},
        cash=Decimal("50000"),
        max_cash_allocation=Decimal("0.90"),
        equity=Decimal("50000"),
        max_cash_reserve=Decimal("70000"),
    )

    assert targets == {
        "AAPL": Decimal("22500.00"),
        "TSLA": Decimal("-22500.00"),
    }


def test_cash_reserve_increases_only_positive_targets_when_ceiling_is_exceeded():
    targets = conviction_targets(
        {"AAPL": "Buy", "MSFT": "Overweight", "TSLA": "Sell"},
        cash=Decimal("50000"),
        max_cash_allocation=Decimal("0.90"),
        equity=Decimal("100000"),
        max_cash_reserve=Decimal("70000"),
    )

    assert targets == {
        "AAPL": Decimal("32000"),
        "MSFT": Decimal("16000"),
        "TSLA": Decimal("-18000"),
    }
    assert Decimal("100000") - sum(targets.values()) == Decimal("70000")


def test_cash_reserve_does_not_invent_longs_for_short_only_decisions():
    targets = conviction_targets(
        {"AAPL": "Sell", "MSFT": "Underweight", "TSLA": "Hold"},
        cash=Decimal("100000"),
        max_cash_allocation=Decimal("0.90"),
        equity=Decimal("100000"),
        max_cash_reserve=Decimal("70000"),
    )

    assert targets == {
        "AAPL": Decimal("-60000"),
        "MSFT": Decimal("-30000"),
        "TSLA": Decimal("0"),
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"cash": Decimal("NaN")}, "cash must be finite"),
        ({"cash": Decimal("Infinity")}, "cash must be finite"),
        ({"equity": Decimal("NaN")}, "equity.*finite"),
        ({"equity": Decimal("Infinity")}, "equity.*finite"),
        ({"equity": Decimal("0")}, "equity.*positive.*finite"),
        ({"max_cash_reserve": Decimal("NaN")}, "max_cash_reserve must be finite"),
        ({"max_cash_reserve": Decimal("Infinity")}, "max_cash_reserve must be finite"),
    ],
)
def test_conviction_targets_reject_invalid_numeric_policy_inputs(overrides, message):
    values = {
        "cash": Decimal("100000"),
        "max_cash_allocation": Decimal("0.90"),
        "equity": Decimal("100000"),
        "max_cash_reserve": Decimal("70000"),
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        conviction_targets({"AAPL": "Buy"}, **values)


def test_risk_policy_constrains_reserve_driven_leveraged_targets_before_intents():
    reserve_targets = conviction_targets(
        {"AAPL": "Buy", "TSLA": "Sell"},
        cash=Decimal("10000"),
        max_cash_allocation=Decimal("0.90"),
        equity=Decimal("100000"),
        max_cash_reserve=Decimal("70000"),
    )
    assert reserve_targets["AAPL"] == Decimal("34500")
    assert reserve_targets["AAPL"] > Decimal("10000")
    assert Decimal("100000") - sum(reserve_targets.values()) == Decimal("70000")

    start = date(2026, 7, 1)
    histories = {}
    for symbol, magnitude in (("AAPL", Decimal("1")), ("TSLA", Decimal("2"))):
        price = Decimal("100")
        rows = [(start, price)]
        for index in range(40):
            change = Decimal("0.05") * magnitude * (1 if index % 2 == 0 else -1)
            price *= Decimal("1") + change
            rows.append((start + timedelta(days=index + 1), price))
        histories[symbol] = tuple(rows)

    scaled = scale_equity_targets(
        reserve_targets,
        {},
        Decimal("100000"),
        histories,
        Decimal("0.15"),
        Decimal("0.20"),
        Decimal("2.0"),
    )
    intents = reconcile_targets(scaled.targets, {}, {}, Decimal("10"))
    buy_notional = sum(
        (intent.notional for intent in intents if intent.side == "buy"), Decimal("0")
    )

    assert scaled.scale < Decimal("1")
    assert scaled.forecast_volatility <= Decimal("0.1500000001")
    assert scaled.gross_leverage <= Decimal("2.0")
    assert {intent.symbol: intent.target_notional for intent in intents} == scaled.targets
    assert buy_notional <= Decimal("50000")


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
