"""Integration tests for Polymarket Gamma API (real network calls).

Run with:
    pytest -m polymarket -v
"""

import pytest
import requests

from tradingagents.signals.polymarket import (
    GAMMA_API_URL,
    fetch_polymarket_signals,
    search_ticker_contracts,
)

pytestmark = pytest.mark.polymarket


def test_gamma_api_reachable():
    resp = requests.get(f"{GAMMA_API_URL}/markets", params={"limit": 1, "active": "true"}, timeout=15)
    assert resp.status_code == 200


def test_fetch_real_signals():
    result = fetch_polymarket_signals(max_signals=5)
    assert isinstance(result["signals"], list)
    assert isinstance(result["fetched_at"], str)
    for s in result["signals"]:
        assert "event" in s
        assert "probability" in s
        assert "volume" in s
        assert "category" in s
        assert "end_date" in s
        assert 0.0 <= s["probability"] <= 1.0


def test_search_real_ticker():
    contracts = search_ticker_contracts("NVDA", "NVIDIA")
    assert isinstance(contracts, list)
    if contracts:
        for c in contracts:
            assert "id" in c
            assert "question" in c
            assert "probability" in c
            assert "liquidity" in c
            assert "active" in c
