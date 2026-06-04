import asyncio
import pytest
import logging
from fastapi.testclient import TestClient

from web.server.app import create_app
from web.server import llm_calls, runner, storage


@pytest.fixture
def client(data_root, monkeypatch):
    """FastAPI TestClient with file-backed storage configured.

    Patches the runner's enqueue() to a no-op fake so the worker does
    not race with the API tests that are asserting the HTTP contract.
    Worker processing is covered by web/server/tests/test_runner.py.
    """
    async def fake_enqueue(ticker, date_str, force=False):
        ticker_u = ticker.upper()
        # Mirror real enqueue: if today's run exists (any status), it's
        # the idempotency anchor; only create a fresh run when force=true
        # (which first supersedes today's existing partial).
        todays = [
            r for r in storage.list_ticker_runs(ticker_u)
            if (r.get("started_at") or "").startswith(date_str)
        ]
        if todays and not force:
            return todays[0]["id"]
        if todays and force:
            for r in todays:
                storage.mark_run_superseded(r["id"])
        return storage.create_run_dir(ticker_u)["run_id"]

    monkeypatch.setattr(runner, "enqueue", fake_enqueue)
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "watchlist_size" in body


def test_lifespan_silences_yfinance_logger(client):
    """The lifespan suppresses yfinance's own ERROR-level noise for
    delisted/foreign symbols (e.g. "TA125: possibly delisted"). Without
    this, the dashboard log fills with yfinance-internal tracebacks
    every poll for every bad ticker in the watchlist."""
    assert logging.getLogger("yfinance").level >= logging.WARNING


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


def test_post_watchlist_rejects_unknown_ticker(client, monkeypatch):
    """POST /api/watchlist must validate the ticker against yfinance.
    Unknown / delisted symbols (e.g. TA125) must be rejected with a
    clear 400 so the user gets immediate feedback instead of a silent
    'stale' state in the price feed."""
    from web.server import price_feed

    # Make yfinance return no usable price for "BADX".
    def _raise(_key, default=None):
        raise KeyError("exchangeTimezoneName")  # mirrors TA125

    fast_info = type("FI", (), {"get": staticmethod(_raise)})()
    ticker_obj = type("T", (), {"fast_info": fast_info})()
    monkeypatch.setattr(price_feed.yf, "Ticker", staticmethod(lambda _t: ticker_obj))

    r = client.post("/api/watchlist", json={"ticker": "BADX", "company_name": "", "exchange": ""})
    assert r.status_code == 400
    body = r.json()["detail"]
    assert body["error"] == "ticker_not_found"
    assert body["ticker"] == "BADX"
    # And the ticker was NOT added.
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    assert r.json() == []


def test_post_watchlist_rejects_zero_price_ticker(client, monkeypatch):
    """yfinance returns lastPrice=0 for some symbols (no trades today).
    Those must be rejected too — a ticker with no live price isn't
    useful in the dashboard."""
    from web.server import price_feed

    fi = type("FI", (), {"get": staticmethod(lambda k, d=None: {"lastPrice": 0.0, "previousClose": 100.0}.get(k, d))})()
    ticker_obj = type("T", (), {"fast_info": fi})()
    monkeypatch.setattr(price_feed.yf, "Ticker", staticmethod(lambda _t: ticker_obj))

    r = client.post("/api/watchlist", json={"ticker": "DEAD", "company_name": "", "exchange": ""})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "ticker_not_found"


def test_runs_lifecycle(client):
    r = client.post("/api/runs", json={"ticker": "NVDA"})
    # The new app uses 202 Accepted (the run is queued, not yet done).
    assert r.status_code == 202
    rid = r.json()["run_id"]
    assert isinstance(rid, str) and rid

    r = client.get(f"/api/runs/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "NVDA"
    assert body["events"] == []  # worker bypassed; no events emitted
    assert body["llm_calls"] == []

    r = client.get("/api/tickers/NVDA/runs")
    assert r.status_code == 200
    assert len(r.json()) >= 1


class TestForceRerun:
    """POST /api/runs accepts a ``force`` flag that bypasses the
    per-day idempotency key so users can rerun an analysis for a
    ticker without waiting until tomorrow."""

    def test_post_run_without_force_is_idempotent_per_day(self, client):
        r1 = client.post("/api/runs", json={"ticker": "NVDA"})
        rid_1 = r1.json()["run_id"]
        # The first run is in "running" status (worker was bypassed, so
        # nothing advanced it). Mark it done so the next call sees a
        # terminal existing run and returns it via the idempotency
        # short-circuit.
        storage.mark_run_status(
            rid_1,
            status="done",
            decision_action="HOLD",
            decision_target=None,
            decision_rationale="",
            decision_confidence=0.0,
        )
        r2 = client.post("/api/runs", json={"ticker": "NVDA"})
        rid_2 = r2.json()["run_id"]
        assert rid_1 == rid_2  # same day, same run is returned

    def test_post_run_with_force_creates_new_run(self, client):
        r1 = client.post("/api/runs", json={"ticker": "NVDA"})
        rid_1 = r1.json()["run_id"]
        r2 = client.post("/api/runs", json={"ticker": "NVDA", "force": True})
        rid_2 = r2.json()["run_id"]
        assert rid_1 != rid_2  # force created a new run

    @pytest.mark.asyncio
    async def test_runner_enqueue_passes_force_to_storage(self, data_root, monkeypatch):
        """The runner's enqueue() must honor ``force=True`` to supersede
        today's partial run and create a new one."""
        from unittest.mock import AsyncMock, MagicMock
        from web.server import runner
        # Replace the queue with an AsyncMock so the put() call is awaitable
        # but the worker never actually runs.
        fake_queue = MagicMock()
        fake_queue.put = AsyncMock()
        monkeypatch.setattr(runner, "_WORK_QUEUE", fake_queue)

        rid1 = await runner.enqueue("AAPL", storage.today_utc_iso())
        rid2 = await runner.enqueue("AAPL", storage.today_utc_iso(), force=True)
        assert rid1 != rid2


class TestTickerRunsList:
    """GET /api/tickers/{ticker}/runs returns the historical run list
    used by the TickerHeader dropdown selector."""

    def test_returns_runs_for_ticker_in_descending_order(self, client):
        # Clear any runs from prior tests in the data dir so the
        # descending-order assertion only sees the runs we create here.
        ticker_dir = storage.data_dir() / "NVDA"
        if ticker_dir.exists():
            import shutil
            shutil.rmtree(ticker_dir)
        # Create three runs for NVDA in chronological order.
        r1 = storage.create_run_dir("NVDA")["run_id"]
        r2 = storage.create_run_dir("NVDA")["run_id"]
        r3 = storage.create_run_dir("NVDA")["run_id"]
        # And one for a different ticker that must NOT appear.
        storage.create_run_dir("AAPL")

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

    def test_get_run_includes_llm_calls_array(self, client, data_root):
        from datetime import datetime, timezone
        rid = storage.create_run_dir("NVDA")["run_id"]
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
        rid = storage.create_run_dir("AAPL")["run_id"]
        r = client.get(f"/api/runs/{rid}")
        assert r.status_code == 200
        assert r.json()["llm_calls"] == []
