"""Meta endpoints: providers + key status, resolve-ticker, defaults."""
from __future__ import annotations


def test_providers_requires_auth(client):
    assert client.get("/api/providers").status_code == 401


def test_providers_lists_known(auth_client):
    data = auth_client.get("/api/providers").json()
    assert "doubao" in data and "qwen" in data
    assert "models" in data["doubao"] and "key_present" in data["doubao"]


def test_resolve_ticker(auth_client, monkeypatch):
    import server.routers.meta as meta
    monkeypatch.setattr(meta, "resolve_ticker", lambda q: ("AAPL", "苹果 → AAPL"))
    r = auth_client.get("/api/resolve-ticker", params={"q": "苹果"})
    assert r.status_code == 200
    assert r.json() == {"ticker": "AAPL", "message": "苹果 → AAPL"}


def test_defaults(auth_client):
    d = auth_client.get("/api/defaults").json()
    assert d["provider"] and "selected_analysts" in d
