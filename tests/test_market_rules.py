"""A Vietnamese stock carries Vietnam's trading rules into every agent's prompt.

Without them the agents plan as if the market were the US one: a next-morning
stop-loss under T+2 settlement, a short sale, a target past the daily band.
"""

import pytest

from tradingagents.agents.context import (
    build_instrument_context,
    get_instrument_context_from_state,
)
from tradingagents.agents.market_rules import market_rules


@pytest.mark.unit
@pytest.mark.parametrize("ticker", ["VCB.VN", "fpt.vn"])
def test_a_vietnamese_stock_gets_the_rules_a_plan_must_respect(ticker):
    rules = market_rules(ticker)

    assert "T+2" in rules
    assert "7%" in rules and "10% on HNX" in rules and "15% on UPCoM" in rules
    assert "board lots of 100" in rules
    assert "cannot be sold short" in rules


@pytest.mark.unit
@pytest.mark.parametrize("ticker", ["AAPL", "7203.T", "0700.HK", "VNM", "BRK.B"])
def test_other_markets_get_no_rules(ticker):
    assert market_rules(ticker) == ""


@pytest.mark.unit
def test_the_instrument_context_carries_the_rules():
    context = build_instrument_context("VCB.VN", "stock", {"company_name": "Vietcombank"})

    assert "Company: Vietcombank" in context
    assert context.endswith(market_rules("VCB.VN"))


@pytest.mark.unit
def test_a_state_without_a_precomputed_context_still_carries_the_rules():
    context = get_instrument_context_from_state({"company_of_interest": "HPG.VN"})

    assert "T+2" in context


@pytest.mark.unit
def test_a_us_stock_context_is_unchanged():
    assert "Vietnam" not in build_instrument_context("AAPL")
