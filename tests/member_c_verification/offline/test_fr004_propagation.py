"""SEL-TA-FR-004 — Propagate explicit context without inventing holdings.

Fit: no-portfolio, explicit flat, held ticker, broker-alias ticker and
null-cash fixtures each preserve their distinct state; missing cash renders no
invented number; unrelated holdings do not leak into another selection.

Enforcing design: RunContext + PortfolioContext rendering semantics
(INV-02/INV-13). Tested at the context/render seam, not the LLM.
"""

from __future__ import annotations

import pytest

from tradingagents.agents.context import get_portfolio_context_from_state
from tradingagents.portfolio import PortfolioContext
from tradingagents.runapi.input_service import freeze_explicit

pytestmark = pytest.mark.unit

DATE = "2026-11-12"


# TC-FR004-a: a no-portfolio run renders the frozen notice, not a flat book.
def test_tc_fr004_a_no_portfolio_notice():
    block = get_portfolio_context_from_state({})
    assert "no account ownership is assumed" in block.lower()
    assert "current position" not in block.lower()


# TC-FR004-b: an explicit flat book says "no current position" (distinct from absent).
def test_tc_fr004_b_explicit_flat_is_distinct():
    block = PortfolioContext.model_validate({"positions": []}).render("AAPL")
    assert "No current position in AAPL" in block


# TC-FR004-c: a held ticker renders the holding and cash; missing cash invents no number.
def test_tc_fr004_c_held_and_missing_cash():
    with_cash = PortfolioContext.model_validate(
        {"cash": 5000.0, "positions": [{"ticker": "AAPL", "quantity": 10}]}).render("AAPL")
    no_cash = PortfolioContext.model_validate(
        {"positions": [{"ticker": "AAPL", "quantity": 10}]}).render("AAPL")
    assert "10" in with_cash and "5,000" in with_cash
    assert "Cash" not in no_cash and "10" in no_cash


# TC-FR004-d: a broker-alias holding is matched to the analyzed instrument.
def test_tc_fr004_d_broker_alias_matched():
    block = PortfolioContext.model_validate(
        {"positions": [{"ticker": "BTCUSDT", "quantity": 2}]}).render("BTC-USD")
    assert "Current position in BTC-USD: 2 units" in block


# TC-FR004-e: selecting one snapshot does not leak another selection's holdings.
def test_tc_fr004_e_no_cross_selection_leak():
    a = freeze_explicit("AAPL", DATE, PortfolioContext.model_validate(
        {"positions": [{"ticker": "AAPL", "quantity": 1}]}))
    b = freeze_explicit("AAPL", DATE, PortfolioContext.model_validate(
        {"positions": [{"ticker": "MSFT", "quantity": 7}]}))
    a_render = a.portfolio_context().render("AAPL")
    b_render = b.portfolio_context().render("AAPL")
    assert "MSFT" not in a_render
    assert "MSFT" in b_render
