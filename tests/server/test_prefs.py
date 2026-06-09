"""Prefs round-trip + research list/delete with stubbed ingest."""
from __future__ import annotations


def test_prefs_roundtrip(auth_client):
    got = auth_client.get("/api/prefs").json()
    assert "tickers" in got
    got["tickers"] = ["NVDA", "AAPL"]
    got["daily_schedule_enabled"] = True
    auth_client.put("/api/prefs", json=got)
    again = auth_client.get("/api/prefs").json()
    assert again["tickers"] == ["NVDA", "AAPL"]
    assert again["daily_schedule_enabled"] is True


def test_research_list_empty(auth_client):
    r = auth_client.get("/api/research", params={"ticker": "NVDA"})
    assert r.status_code == 200
    assert r.json() == []


def test_checkpoint_status(auth_client):
    r = auth_client.get("/api/checkpoints", params={"ticker": "NVDA", "date": "2026-06-09"})
    assert r.status_code == 200
    assert r.json()["resumable"] is False
