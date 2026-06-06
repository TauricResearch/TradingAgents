"""Tests for the options-chain tool (selection logic, offline)."""

from __future__ import annotations

import pytest

from tradingagents.tools import get_options_chain, select_contract

pytestmark = pytest.mark.unit


def _chain():
    return [
        {"strike": 90, "option_type": "call"},
        {"strike": 100, "option_type": "call"},
        {"strike": 110, "option_type": "call"},
    ]


def test_get_options_chain_injected():
    chain = get_options_chain("AAPL", option_type="call", live_fn=lambda s, t, e: _chain())
    assert len(chain) == 3
    # no source -> empty
    assert get_options_chain("AAPL", option_type="call") == []


def test_select_contract_nearest_strike():
    assert select_contract(_chain(), target_strike=103)["strike"] == 100
    assert select_contract(_chain(), target_strike=108)["strike"] == 110
    assert select_contract([], target_strike=100) is None
