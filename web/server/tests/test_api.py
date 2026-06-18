"""Integration tests for API endpoints (watchlist, runs, config, etc.)."""
from __future__ import annotations


def test_ticker_agent_status(client):
    r = client.get("/api/ticker-agent/status")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
