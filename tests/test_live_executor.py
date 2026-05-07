"""Tests for the live-execution safety gates.

These tests verify that the module REFUSES to place real orders unless the
caller has explicitly opted in across all required surfaces. The tests do
NOT exercise real order placement.
"""

import pytest

from tradingagents.agents.schemas import PolymarketDecision, PolymarketDirection
from tradingagents.exchange.live_executor import (
    LiveExecutionDisabled,
    place_order,
)


def _decision(direction: str = "BUY_YES") -> PolymarketDecision:
    return PolymarketDecision(
        market_id="540816",
        question="Will X happen by Y date?",
        direction=PolymarketDirection(direction),
        confidence=0.7,
        rationale="synthetic test rationale",
        yes_price_at_analysis=0.40,
        cycle_ts=12345,
    )


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch):
    """Default: clear all live-related env vars so gates start as fail-closed."""
    monkeypatch.delenv("POLYMARKET_LIVE", raising=False)
    monkeypatch.delenv("POLYMARKET_PRIVATE_KEY", raising=False)


@pytest.mark.unit
def test_default_call_is_disabled():
    """Calling without confirm_real_money is the safest possible mistake."""
    r = place_order(
        _decision(),
        budget_usd=100.0,
        yes_token_id="850149...",
        no_token_id="294612...",
    )
    assert r["status"] == "LIVE_DISABLED"
    assert "confirm_real_money" in r["reason"]
    assert r["order_id"] is None


@pytest.mark.unit
def test_confirm_flag_alone_is_not_enough():
    """confirm_real_money=True without env vars must still be blocked."""
    r = place_order(
        _decision(),
        budget_usd=100.0,
        yes_token_id="850149...",
        no_token_id="294612...",
        confirm_real_money=True,
    )
    assert r["status"] == "LIVE_DISABLED"
    assert "POLYMARKET_LIVE" in r["reason"]


@pytest.mark.unit
def test_polymarket_live_alone_is_not_enough(monkeypatch):
    """POLYMARKET_LIVE=1 without private key must still be blocked."""
    monkeypatch.setenv("POLYMARKET_LIVE", "1")
    r = place_order(
        _decision(),
        budget_usd=100.0,
        yes_token_id="850149...",
        no_token_id="294612...",
        confirm_real_money=True,
    )
    assert r["status"] == "LIVE_DISABLED"
    assert "POLYMARKET_PRIVATE_KEY" in r["reason"]


@pytest.mark.unit
def test_all_env_gates_pass_then_blocked_by_dependency_or_stub(monkeypatch):
    """With all env vars set, py-clob-client missing should still block.

    If py-clob-client IS installed locally, the stub raises
    LiveExecutionDisabled instead. Either way, no real order leaks through.
    """
    monkeypatch.setenv("POLYMARKET_LIVE", "1")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "00" * 32)

    try:
        import py_clob_client  # noqa: F401
        py_clob_installed = True
    except ImportError:
        py_clob_installed = False

    if py_clob_installed:
        with pytest.raises(LiveExecutionDisabled):
            place_order(
                _decision(),
                budget_usd=100.0,
                yes_token_id="850149...",
                no_token_id="294612...",
                confirm_real_money=True,
            )
    else:
        r = place_order(
            _decision(),
            budget_usd=100.0,
            yes_token_id="850149...",
            no_token_id="294612...",
            confirm_real_money=True,
        )
        assert r["status"] == "LIVE_DISABLED"
        assert "py-clob-client" in r["reason"]


@pytest.mark.unit
def test_hold_decision_is_skipped_not_disabled():
    """HOLD never tries to place an order; should return LIVE_SKIPPED."""
    r = place_order(
        _decision(direction="HOLD"),
        budget_usd=100.0,
        yes_token_id="850149...",
        no_token_id="294612...",
        confirm_real_money=True,
    )
    assert r["status"] == "LIVE_SKIPPED"
    assert "HOLD" in r["reason"]
