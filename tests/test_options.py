from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tradingagents.options import (
    EquityPosition,
    OptionContract,
    OptionIntent,
    OptionOpenOrder,
    OptionPosition,
    build_reservations,
    contract_metrics,
    option_delta_exposure,
    option_intent_delta_exposure,
    plan_new_entry,
    plan_profit_exit,
    select_contract,
)

NOW = datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)


def _contract(
    symbol="AAPL261002P00300000",
    kind="put",
    strike="300",
    delta="-0.20",
    expiration=date(2026, 10, 2),
):
    return OptionContract(
        symbol=symbol,
        underlying="AAPL",
        kind=kind,
        strike=Decimal(strike),
        expiration=expiration,
        delta=Decimal(delta),
        bid=Decimal("3.00"),
        ask=Decimal("3.20"),
        open_interest=Decimal("500"),
        quote_time=NOW,
    )


def test_contract_metrics_use_new_york_trade_date_and_reviewed_formulas():
    contract = _contract(expiration=date(2026, 9, 18))
    annualized_yield, score, dte = contract_metrics(contract, NOW)
    assert dte == 14
    assert annualized_yield == Decimal("0.2433333333333333333333333333")
    assert score == Decimal("0.1052631578947368421052631579")


def test_select_contract_uses_reviewed_filters_and_highest_score():
    lower = _contract()
    higher = _contract(symbol="AAPL261002P00310000", strike="310")
    assert select_contract((lower, higher), NOW, date(2026, 12, 1)).symbol == lower.symbol


def test_select_contract_breaks_equal_scores_by_highest_symbol():
    first = _contract(symbol="AAPL261002P00300000")
    second = replace(first, symbol="AAPL261002P00300001")
    assert select_contract((first, second), NOW, None).symbol == second.symbol


@pytest.mark.parametrize(
    ("changes", "accepted"),
    [
        ({"expiration": date(2026, 9, 18)}, True),
        ({"expiration": date(2026, 10, 2)}, True),
        ({"expiration": date(2026, 9, 17)}, False),
        ({"expiration": date(2026, 10, 3)}, False),
        ({"delta": Decimal("-0.15")}, True),
        ({"delta": Decimal("-0.30")}, True),
        ({"delta": Decimal("-0.149")}, False),
        ({"delta": Decimal("-0.301")}, False),
        ({"open_interest": Decimal("101")}, True),
        ({"open_interest": Decimal("100")}, False),
    ],
)
def test_select_contract_enforces_dte_delta_and_open_interest_boundaries(changes, accepted):
    result = select_contract((replace(_contract(), **changes),), NOW, None)
    assert (result is not None) is accepted


def test_select_contract_rejects_yield_and_score_boundaries(monkeypatch):
    values = iter(
        (
            (Decimal("0.04"), Decimal("0.06"), 20),
            (Decimal("1.00"), Decimal("0.06"), 20),
            (Decimal("0.05"), Decimal("0.05"), 20),
        )
    )
    monkeypatch.setattr(
        "tradingagents.options.contract_metrics", lambda contract, now: next(values)
    )
    assert select_contract((_contract(),), NOW, None) is None
    assert select_contract((_contract(),), NOW, None) is None
    assert select_contract((_contract(),), NOW, None) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"quote_time": None},
        {"quote_time": NOW + timedelta(seconds=1)},
        {"quote_time": NOW - timedelta(seconds=301)},
        {"bid": Decimal("0")},
        {"ask": Decimal("0")},
        {"bid": Decimal("3.21")},
        {"strike": Decimal("0")},
    ],
)
def test_select_contract_rejects_invalid_quotes(changes):
    assert select_contract((replace(_contract(), **changes),), NOW, None) is None


def test_select_contract_accepts_quote_exactly_300_seconds_old():
    contract = replace(_contract(), quote_time=NOW - timedelta(seconds=300))
    assert select_contract((contract,), NOW, None) == contract


@pytest.mark.parametrize(
    ("earnings", "accepted"),
    [(date(2026, 9, 11), False), (date(2026, 9, 12), True), (date(2026, 9, 3), True)],
)
def test_select_contract_enforces_seven_day_earnings_blackout(earnings, accepted):
    assert (select_contract((_contract(),), NOW, earnings) is not None) is accepted


def test_short_put_and_covered_call_reservations_are_reconstructed():
    reservations = build_reservations(
        equities=(EquityPosition("AAPL", Decimal("250"), Decimal("300"), Decimal("320")),),
        options=(
            OptionPosition(
                "AAPL261002P00300000", "AAPL", "put", Decimal("-1"), Decimal("3"), Decimal("-0.2")
            ),
        ),
        orders=(
            OptionOpenOrder(
                "AAPL261002C00350000",
                "AAPL",
                "call",
                "sell_to_open",
                Decimal("1"),
                Decimal("0"),
                Decimal("350"),
            ),
        ),
    )
    assert reservations.put_collateral["AAPL"] == Decimal("30000")
    assert reservations.covered_shares["AAPL"] == Decimal("100")


def test_remaining_sell_to_open_put_order_reserves_collateral():
    reservations = build_reservations(
        (),
        (),
        (
            OptionOpenOrder(
                "AAPL261002P00300000",
                "AAPL",
                "put",
                "sell_to_open",
                Decimal("1"),
                Decimal("0.25"),
                Decimal("300"),
            ),
        ),
    )
    assert reservations.put_collateral == {"AAPL": Decimal("22500.00")}


def test_unrelated_short_equity_does_not_invalidate_covered_call():
    reservations = build_reservations(
        (
            EquityPosition("AAPL", Decimal("100"), Decimal("300"), Decimal("320")),
            EquityPosition("TSLA", Decimal("-10"), Decimal("250"), Decimal("240")),
        ),
        (
            OptionPosition(
                "AAPL261002C00350000", "AAPL", "call", Decimal("-1"), Decimal("3"), Decimal("0.2")
            ),
        ),
        (),
    )
    assert reservations.covered_shares == {"AAPL": Decimal("100")}


def test_same_underlying_short_equity_reduces_call_coverage():
    equities = (
        EquityPosition("AAPL", Decimal("100"), Decimal("300"), Decimal("320")),
        EquityPosition("AAPL", Decimal("-50"), Decimal("330"), Decimal("320")),
    )
    call = OptionPosition(
        "AAPL261002C00350000", "AAPL", "call", Decimal("-1"), Decimal("3"), Decimal("0.2")
    )
    with pytest.raises(ValueError):
        build_reservations(equities, (call,), ())


@pytest.mark.parametrize(
    ("equities", "options", "orders"),
    [
        (
            (),
            (OptionPosition("C", "AAPL", "call", Decimal("-1"), Decimal("3"), Decimal("0.2")),),
            (),
        ),
        (
            (EquityPosition("AAPL", Decimal("-100"), Decimal("300"), Decimal("320")),),
            (OptionPosition("C", "AAPL", "call", Decimal("-1"), Decimal("3"), Decimal("0.2")),),
            (),
        ),
        (
            (EquityPosition("AAPL", Decimal("100"), Decimal("300"), Decimal("320")),),
            (OptionPosition("C", "AAPL", "call", Decimal("-2"), Decimal("3"), Decimal("0.2")),),
            (),
        ),
        (
            (),
            (
                OptionPosition("P1", "AAPL", "put", Decimal("-1"), Decimal("3"), Decimal("-0.2")),
                OptionPosition("P2", "AAPL", "put", Decimal("-1"), Decimal("3"), Decimal("-0.2")),
            ),
            (),
        ),
        (
            (),
            (),
            (
                OptionOpenOrder(
                    "P", "AAPL", "put", "sell_to_open", Decimal("2"), Decimal("0"), Decimal("300")
                ),
            ),
        ),
    ],
)
def test_reservations_reject_uncovered_or_more_than_one_active_contract(equities, options, orders):
    with pytest.raises(ValueError):
        build_reservations(equities, options, orders)


def test_short_put_has_positive_delta_equivalent_exposure():
    position = OptionPosition(
        "AAPL261002P00300000", "AAPL", "put", Decimal("-1"), Decimal("3"), Decimal("-0.20")
    )
    assert option_delta_exposure((position,), {"AAPL": Decimal("320")}) == {
        "AAPL": Decimal("6400.00")
    }


def test_option_intent_delta_exposure_uses_buy_and_sell_contract_signs():
    buy = OptionIntent(
        "P", "AAPL", "put", "buy", "buy_to_close", Decimal("1"), Decimal("2"), Decimal("-0.20")
    )
    sell = replace(buy, side="sell", position_intent="sell_to_open")
    assert option_intent_delta_exposure((buy, sell), {"AAPL": Decimal("320")}) == {
        "AAPL": Decimal("0.00")
    }


def test_profit_exit_buys_back_at_half_the_opening_credit():
    position = OptionPosition(
        "AAPL261002P00300000", "AAPL", "put", Decimal("-1"), Decimal("4.00"), Decimal("-0.20")
    )
    contract = replace(_contract(), bid=Decimal("1.80"), ask=Decimal("2.00"))
    intent = plan_profit_exit(position, contract, NOW)
    assert intent.side == "buy"
    assert intent.position_intent == "buy_to_close"
    assert intent.limit_price == Decimal("2.00")


def test_profit_exit_rejects_above_half_credit_and_invalid_current_quote():
    position = OptionPosition(
        "AAPL261002P00300000", "AAPL", "put", Decimal("-1"), Decimal("4.00"), Decimal("-0.20")
    )
    assert plan_profit_exit(position, replace(_contract(), ask=Decimal("2.01")), NOW) is None
    assert (
        plan_profit_exit(
            position,
            replace(_contract(), ask=Decimal("2.00"), quote_time=NOW - timedelta(seconds=301)),
            NOW,
        )
        is None
    )


def test_put_requires_buy_or_overweight_and_empty_underlying():
    assert (
        plan_new_entry("AAPL", "Hold", (), (), (), (), NOW, date(2026, 12, 1), Decimal("200000"))
        is None
    )


def test_buy_signal_opens_cash_secured_put():
    intent = plan_new_entry("AAPL", "Buy", (), (), (), (_contract(),), NOW, None, Decimal("30000"))
    assert intent.kind == "put"
    assert intent.qty == Decimal("1")
    assert intent.limit_price == Decimal("3.10")


def test_put_entry_requires_cash_and_no_active_underlying():
    active = OptionPosition(
        "AAPL261002P00300000", "AAPL", "put", Decimal("-1"), Decimal("3"), Decimal("-0.2")
    )
    assert (
        plan_new_entry("AAPL", "Buy", (), (), (), (_contract(),), NOW, None, Decimal("29999.99"))
        is None
    )
    assert (
        plan_new_entry(
            "AAPL", "Buy", (), (active,), (), (_contract(),), NOW, None, Decimal("50000")
        )
        is None
    )


def test_call_requires_reserved_long_lot_and_hold_or_underweight():
    call = _contract("AAPL261002C00350000", "call", "350", "0.20")
    equity = EquityPosition("AAPL", Decimal("100"), Decimal("300"), Decimal("320"))
    intent = plan_new_entry(
        "AAPL", "Hold", (equity,), (), (), (call,), NOW, date(2026, 12, 1), Decimal("200000")
    )
    assert intent.position_intent == "sell_to_open"
    assert intent.kind == "call"
    assert intent.limit_price == Decimal("3.10")


def test_call_entry_rejects_buy_signal_or_insufficient_unreserved_shares():
    call = _contract("AAPL261002C00350000", "call", "350", "0.20")
    equity = EquityPosition("AAPL", Decimal("100"), Decimal("300"), Decimal("320"))
    assert (
        plan_new_entry("AAPL", "Buy", (equity,), (), (), (call,), NOW, None, Decimal("200000"))
        is None
    )
    existing = OptionPosition("C", "AAPL", "call", Decimal("-1"), Decimal("3"), Decimal("0.2"))
    assert (
        plan_new_entry(
            "AAPL", "Hold", (equity,), (existing,), (), (call,), NOW, None, Decimal("200000")
        )
        is None
    )


def test_put_entry_requires_no_equity_position_in_underlying():
    short_equity = EquityPosition("AAPL", Decimal("-10"), Decimal("330"), Decimal("320"))
    assert (
        plan_new_entry(
            "AAPL", "Buy", (short_equity,), (), (), (_contract(),), NOW, None, Decimal("50000")
        )
        is None
    )
