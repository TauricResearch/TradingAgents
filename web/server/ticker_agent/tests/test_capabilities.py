"""Tests for API capabilities inventory."""
from __future__ import annotations

from web.server.ticker_agent.capabilities import discover_api_capabilities, ApiCapability


def test_discover_returns_list():
    caps = discover_api_capabilities()
    assert len(caps) > 0
    assert all(isinstance(c, ApiCapability) for c in caps)


def test_discover_includes_core_endpoints():
    caps = discover_api_capabilities()
    paths = {c.path for c in caps}
    assert "/api/runs" in paths
    assert "/api/watchlist" in paths
    assert "/api/tickers/{ticker}/history" in paths
