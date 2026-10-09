"""Fail-closed paper trade guard; no LLMs, exchange keys or network needed."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tradingagents.trade_guard import (
    MarketSnapshot,
    PortfolioSnapshot,
    TradeIntent,
    validate_intent,
)

NOW = datetime(2026, 10, 9, 16, 0, tzinfo=UTC)


def market(**overrides):
    params = {"symbol": "BTC-USD", "price": "82403.44", "observed_at": NOW, "source": "exchange"}
    params.update(overrides)
    return MarketSnapshot(**params)


def portfolio(**overrides):
    params = {"equity_quote": "100000", "free_quote": "10000", "free_base": "0.3"}
    params.update(overrides)
    return PortfolioSnapshot(**params)


def intent(**overrides):
    params = {
        "symbol": "BTC-USD",
        "market": "PERPETUAL",
        "action": "SHORT_OPEN",
        "order_type": "LIMIT",
        "quantity_base": "0.025",
        "limit_price": "84500",
        "stop_loss": "87800",
        "take_profit": "80000",
        "idempotency_key": "analysis-20261009-btc-01",
    }
    params.update(overrides)
    return TradeIntent(**params)


@pytest.mark.unit
def test_well_defined_unleveraged_short_can_be_proposed_for_paper():
    result = validate_intent(intent(), market(), portfolio(), now=NOW)
    assert result.approved is True
    assert result.reasons == ()
    assert result.notional_quote == Decimal("2112.500")
    assert result.theoretical_stop_loss_quote == Decimal("82.500")


@pytest.mark.unit
@pytest.mark.parametrize("unsupported", ["SELL", "BUY", "SHORT", "SELL_NOW"])
def test_ambiguous_actions_are_not_part_of_contract(unsupported):
    with pytest.raises(ValidationError):
        intent(action=unsupported)


@pytest.mark.unit
def test_real_execution_is_not_an_available_mode():
    with pytest.raises(ValidationError):
        intent(execution_mode="LIVE")


@pytest.mark.unit
def test_spot_short_rejected():
    result = validate_intent(intent(market="SPOT"), market(), portfolio(), now=NOW)
    assert "SHORT_ACTION_REQUIRES_PERPETUAL_MARKET" in result.reasons


@pytest.mark.unit
def test_buy_with_wrong_stop_direction_rejected():
    i = intent(
        market="SPOT", action="SPOT_BUY", order_type="MARKET",
        limit_price=None, stop_loss="90000", take_profit="85000",
    )
    result = validate_intent(i, market(), portfolio(), now=NOW)
    assert "LONG_PRICE_LEVELS_INVALID" in result.reasons


@pytest.mark.unit
def test_short_with_stop_below_entry_rejected():
    result = validate_intent(intent(stop_loss="80000"), market(), portfolio(), now=NOW)
    assert "SHORT_PRICE_LEVELS_INVALID" in result.reasons


@pytest.mark.unit
def test_risk_loss_budget_rejected_even_if_notional_within_cap():
    result = validate_intent(
        intent(quantity_base="0.05", stop_loss="120000"),
        market(), portfolio(), now=NOW,
    )
    assert "LOSS_BUDGET_EXCEEDED" in result.reasons


@pytest.mark.unit
def test_notional_exposure_capped():
    result = validate_intent(
        intent(quantity_base="0.08"), market(), portfolio(), now=NOW,
    )
    assert "NOTIONAL_LIMIT_EXCEEDED" in result.reasons


@pytest.mark.unit
def test_missing_stop_rejected():
    result = validate_intent(intent(stop_loss=None), market(), portfolio(), now=NOW)
    assert "STOP_LOSS_REQUIRED" in result.reasons


@pytest.mark.unit
def test_missing_target_rejected():
    result = validate_intent(intent(take_profit=None), market(), portfolio(), now=NOW)
    assert "TAKE_PROFIT_REQUIRED" in result.reasons


@pytest.mark.unit
def test_stale_market_snapshot_rejected():
    old = NOW - timedelta(minutes=3)
    result = validate_intent(intent(), market(observed_at=old), portfolio(), now=NOW)
    assert "MARKET_SNAPSHOT_STALE" in result.reasons


@pytest.mark.unit
def test_future_market_snapshot_rejected():
    result = validate_intent(
        intent(), market(observed_at=NOW + timedelta(minutes=1)), portfolio(), now=NOW,
    )
    assert "MARKET_SNAPSHOT_FROM_FUTURE" in result.reasons


@pytest.mark.unit
def test_wrong_market_snapshot_rejected():
    result = validate_intent(intent(), market(symbol="ETH-USD"), portfolio(), now=NOW)
    assert "SYMBOL_MISMATCH" in result.reasons


@pytest.mark.unit
def test_market_timestamp_requires_timezone():
    with pytest.raises(ValidationError):
        market(observed_at=datetime(2026, 10, 9, 16, 0))


@pytest.mark.unit
def test_limit_order_requires_price():
    result = validate_intent(intent(limit_price=None), market(), portfolio(), now=NOW)
    assert "LIMIT_PRICE_REQUIRED" in result.reasons


@pytest.mark.unit
def test_market_order_must_not_have_limit_price():
    result = validate_intent(intent(order_type="MARKET"), market(), portfolio(), now=NOW)
    assert "MARKET_ORDER_MUST_NOT_HAVE_LIMIT_PRICE" in result.reasons


@pytest.mark.unit
def test_spot_sale_cannot_sell_more_btc_than_owned():
    i = intent(
        market="SPOT", action="SPOT_SELL", quantity_base="0.5",
        stop_loss=None, take_profit=None,
    )
    result = validate_intent(i, market(), portfolio(), now=NOW)
    assert "BASE_BALANCE_INSUFFICIENT" in result.reasons


@pytest.mark.unit
def test_hold_never_places_order():
    result = validate_intent(
        intent(action="HOLD", order_type=None, quantity_base=None),
        market(), portfolio(), now=NOW,
    )
    assert result.approved is False
    assert result.reasons == ("HOLD_NO_ORDER",)


@pytest.mark.unit
def test_blank_idempotency_key_rejected():
    result = validate_intent(intent(idempotency_key=" "), market(), portfolio(), now=NOW)
    assert "IDEMPOTENCY_KEY_REQUIRED" in result.reasons


@pytest.mark.unit
def test_missing_quote_collateral_rejected():
    result = validate_intent(
        intent(), market(), portfolio(free_quote="100"), now=NOW,
    )
    assert "QUOTE_BALANCE_INSUFFICIENT" in result.reasons


@pytest.mark.unit
def test_leverage_is_disabled_even_in_paper_mode():
    result = validate_intent(
        intent(leverage=2), market(), portfolio(), now=NOW,
    )
    assert "LEVERAGE_NOT_SUPPORTED" in result.reasons


@pytest.mark.unit
def test_short_close_is_not_implemented_yet():
    result = validate_intent(
        intent(action="SHORT_CLOSE"), market(), portfolio(), now=NOW,
    )
    assert "SHORT_CLOSE_NOT_IMPLEMENTED" in result.reasons


@pytest.mark.unit
def test_extra_unverified_fields_are_rejected():
    with pytest.raises(ValidationError):
        intent(llm_confidence=0.99)
