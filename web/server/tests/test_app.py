import pytest
from fastapi.testclient import TestClient

from web.server.app import create_app
from web.server import db, llm_calls


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
        lambda ticker, *, idempotency_key, force=False: db.create_run(
            ticker=ticker, idempotency_key=idempotency_key, force=force
        ),
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


class TestForceRerun:
    """POST /api/runs accepts a ``force`` flag that bypasses the
    per-day idempotency key so users can rerun an analysis for a
    ticker without waiting until tomorrow."""

    def test_post_run_without_force_is_idempotent_per_day(self, client, monkeypatch):
        from web.server import runner
        monkeypatch.setattr(
            runner,
            "enqueue",
            lambda ticker, *, idempotency_key, force=False: db.create_run(
                ticker=ticker, idempotency_key=idempotency_key, force=force
            ),
        )
        r1 = client.post("/api/runs", json={"ticker": "NVDA"})
        rid_1 = r1.json()["run_id"]
        # The first run is in "running" status (worker was bypassed, so
        # nothing advanced it). Mark it done so the next call sees a
        # non-running existing row and returns it via the idempotency
        # short-circuit.
        db.mark_run_done(rid_1, decision_action="HOLD", decision_target=None, decision_rationale="", decision_confidence=0.0)
        r2 = client.post("/api/runs", json={"ticker": "NVDA"})
        rid_2 = r2.json()["run_id"]
        assert rid_1 == rid_2  # same day, same idempotency_key

    def test_post_run_with_force_creates_new_run(self, client, monkeypatch):
        from web.server import runner
        monkeypatch.setattr(
            runner,
            "enqueue",
            lambda ticker, *, idempotency_key, force=False: db.create_run(
                ticker=ticker, idempotency_key=idempotency_key, force=force
            ),
        )
        r1 = client.post("/api/runs", json={"ticker": "NVDA"})
        rid_1 = r1.json()["run_id"]
        r2 = client.post("/api/runs", json={"ticker": "NVDA", "force": True})
        rid_2 = r2.json()["run_id"]
        assert rid_2 > rid_1  # new row was inserted

    def test_runner_enqueue_passes_force_to_db(self, temp_db, monkeypatch):
        """The runner's enqueue() must forward ``force`` to db.create_run
        so a re-run actually creates a new row instead of returning the
        cached one."""
        from unittest.mock import MagicMock
        from web.server import runner
        # Replace the queue with a no-op so the worker doesn't run; we
        # only care about the create_run side-effect of enqueue().
        fake_queue = MagicMock()
        fake_queue.put_nowait = MagicMock()
        monkeypatch.setattr(runner, "_queue", fake_queue)

        rid1 = runner.enqueue("AAPL", idempotency_key="AAPL:rerun-test")
        rid2 = runner.enqueue("AAPL", idempotency_key="AAPL:rerun-test", force=True)
        assert rid2 > rid1


class TestTickerRunsList:
    """GET /api/tickers/{ticker}/runs returns the historical run list
    used by the TickerHeader dropdown selector."""

    def test_returns_runs_for_ticker_in_descending_order(self, client):
        # Create three runs for NVDA in chronological order.
        r1 = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-01-01")
        r2 = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-01-02")
        r3 = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-01-03")
        # And one for a different ticker that must NOT appear.
        db.create_run(ticker="AAPL", idempotency_key="AAPL:2026-01-01")

        r = client.get("/api/tickers/NVDA/runs")
        assert r.status_code == 200
        body = r.json()
        ids = [row["id"] for row in body]
        assert ids == [r3, r2, r1]  # newest first

    def test_empty_for_unknown_ticker(self, client):
        r = client.get("/api/tickers/ZZZZ/runs")
        assert r.status_code == 200
        assert r.json() == []


class TestRunDetailLlmCalls:
    """GET /api/runs/{run_id} must include the persisted LlmCall rows
    so the UI can show the LLM traffic that produced the decision."""

    def test_get_run_includes_llm_calls_array(self, client, temp_db):
        from datetime import datetime, timezone
        rid = db.create_run(ticker="NVDA", idempotency_key="NVDA:llm-detail")
        llm_calls.save_llm_call(
            run_id=rid,
            ticker="NVDA",
            node_name="Market Analyst",
            started_at=datetime.now(timezone.utc),
            model="gpt-4o",
            prompt_text="analyze NVDA",
            response_text="bullish",
            tool_calls=[],
            input_tokens=5,
            output_tokens=3,
            total_tokens=8,
            duration_ms=120,
        )

        r = client.get(f"/api/runs/{rid}")
        assert r.status_code == 200
        body = r.json()
        assert "llm_calls" in body
        assert len(body["llm_calls"]) == 1
        call = body["llm_calls"][0]
        assert call["run_id"] == rid
        assert call["ticker"] == "NVDA"
        assert call["model"] == "gpt-4o"
        assert call["node_name"] == "Market Analyst"
        assert call["input_tokens"] == 5

    def test_get_run_returns_empty_llm_calls_when_none(self, client):
        rid = db.create_run(ticker="AAPL", idempotency_key="AAPL:no-llms")
        r = client.get(f"/api/runs/{rid}")
        assert r.status_code == 200
        assert r.json()["llm_calls"] == []
