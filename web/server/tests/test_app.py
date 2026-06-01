import pytest
from fastapi.testclient import TestClient

from web.server.app import create_app
from web.server import db


@pytest.fixture
def client(temp_db, monkeypatch):
    monkeypatch.setattr("web.server.events._broadcast", lambda rid, evt: None)
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "watchlist_size" in body


def test_watchlist_crud(client):
    r = client.post("/api/watchlist", json={"ticker": "NVDA", "company_name": "NVIDIA", "exchange": "NASDAQ"})
    assert r.status_code == 201
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    assert {row["ticker"] for row in r.json()} == {"NVDA"}

    # duplicate
    r = client.post("/api/watchlist", json={"ticker": "NVDA", "company_name": "NVIDIA", "exchange": "NASDAQ"})
    assert r.status_code == 409

    r = client.delete("/api/watchlist/NVDA")
    assert r.status_code == 204
    assert client.get("/api/watchlist").json() == []


def test_runs_lifecycle(client, monkeypatch):
    from web.server import runner
    # Bypass the queue push so the worker cannot race with the GET below.
    # The route contract under test is that POST returns a run_id and GET returns
    # the run + its events; worker processing is covered by test_runner.py.
    monkeypatch.setattr(
        runner,
        "enqueue",
        lambda ticker, *, idempotency_key: db.create_run(ticker=ticker, idempotency_key=idempotency_key),
    )
    r = client.post("/api/runs", json={"ticker": "NVDA"})
    assert r.status_code == 201
    rid = r.json()["run_id"]
    assert rid > 0

    r = client.get(f"/api/runs/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert body["run"]["ticker"] == "NVDA"
    assert body["events"] == []  # worker bypassed; no events emitted

    r = client.get("/api/runs?limit=10")
    assert r.status_code == 200
    assert len(r.json()) >= 1
