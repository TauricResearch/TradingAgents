import asyncio
import pytest
import logging
from fastapi.testclient import TestClient

from web.server.app import create_app
from web.server import events, llm_calls, runner, storage


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
    # Ticker must be on the watchlist before /api/runs accepts it.
    client.post("/api/watchlist", json={"ticker": "NVDA", "company_name": "NVIDIA", "exchange": "NASDAQ"})
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
        client.post("/api/watchlist", json={"ticker": "NVDA", "company_name": "NVIDIA", "exchange": "NASDAQ"})
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
        client.post("/api/watchlist", json={"ticker": "NVDA", "company_name": "NVIDIA", "exchange": "NASDAQ"})
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


class TestCancelEndpoint:
    """POST /api/runs/{run_id}/cancel sets cancel_requested=True on the
    run.json. The runner observes the flag on the next cb() invocation
    and exits the propagate loop with status=failed + error=cancelled."""

    def test_cancel_marks_run_cancel_requested(self, client):
        rid = storage.create_run_dir("NVDA")["run_id"]
        r = client.post(f"/api/runs/{rid}/cancel")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == rid
        # Persisted flag is set.
        run_json = storage.read_run(rid)
        assert run_json["cancel_requested"] is True

    def test_cancel_unknown_run_returns_404(self, client):
        r = client.post("/api/runs/NOPE:nope/cancel")
        assert r.status_code == 404


class TestPricesEndpoint:
    """GET /api/prices returns the in-memory snapshot of watchlist prices
    maintained by the background ``PriceFeed``. The frontend polls this
    endpoint (and merges WS ``price_update`` events) to render the price
    column on every ticker in the watchlist."""

    def test_prices_empty_dict_when_watchlist_empty(self, client):
        """On a fresh dashboard (no tickers added yet) the route must
        return 200 with an empty object — NOT 404. A 404 here breaks
        the dashboard's initial render before the user has done
        anything."""
        r = client.get("/api/prices")
        assert r.status_code == 200
        assert r.json() == {}

    def test_prices_returns_seeded_snapshot(self, client):
        """The route must surface whatever the in-memory ``PriceState``
        holds. This decouples the route from the feed's poll loop
        (which has its own test suite) while still proving the route
        is wired to the correct state object."""
        from web.server import price_feed
        snap = price_feed.PriceSnapshot(
            price=123.45,
            prev_close=120.0,
            change_pct=2.875,
            sparkline=[120.0, 121.0, 123.45],
            stale=False,
        )
        client.app.state.price_state.snapshots["NVDA"] = snap

        r = client.get("/api/prices")
        assert r.status_code == 200
        body = r.json()
        assert "NVDA" in body
        assert body["NVDA"]["price"] == 123.45
        assert body["NVDA"]["change_pct"] == 2.875
        assert body["NVDA"]["stale"] is False
        assert body["NVDA"]["sparkline"] == [120.0, 121.0, 123.45]

    def test_poll_populates_snapshot_for_added_ticker(self, client, monkeypatch):
        """End-to-end: adding a ticker to the watchlist and running one
        poll iteration must populate its snapshot. This is the exact
        flow the user reported broken ('prices don't start updating
        when a ticker is added'). We mock yfinance so the test is
        deterministic and doesn't hit the network."""
        from web.server import price_feed

        # Mock yfinance fast_info to return a known price for NVDA.
        fi = type("FI", (), {"get": staticmethod(
            lambda k, d=None: {"lastPrice": 500.0, "regularMarketPreviousClose": 490.0}.get(k, d)
        )})()
        ticker_obj = type("T", (), {"fast_info": fi})()
        monkeypatch.setattr(price_feed.yf, "Ticker", staticmethod(lambda _t: ticker_obj))

        # Add the ticker to the watchlist. Patch validate_ticker_exists
        # so the POST /api/watchlist probe (which uses a different
        # yfinance path) accepts the ticker; the mock yfinance above
        # will then drive the actual price feed poll.
        monkeypatch.setattr(price_feed, "validate_ticker_exists", lambda _t: None)
        client.post("/api/watchlist", json={"ticker": "NVDA", "company_name": "NVIDIA", "exchange": "NASDAQ"})

        # Run one poll iteration directly against the wired state.
        asyncio.run(price_feed._poll_once(client.app.state.price_state, broadcast=None))

        r = client.get("/api/prices")
        assert r.status_code == 200
        body = r.json()
        assert "NVDA" in body
        assert body["NVDA"]["price"] == 500.0
        assert body["NVDA"]["stale"] is False


class TestTransparencyEndpoints:
    """GET /api/runs/{id}/trace and /api/runs/{id}/health.

    These power the dashboard's "what's the system doing right now?"
    views. The trace merges events + stages + LLM calls into a single
    chronological timeline; the health endpoint gives a liveness
    snapshot (status, current node, last event age, LLM totals).
    """

    def _seed_run(self, data_root):
        """Create a run with a few events, a stage, and an LLM call."""
        info = storage.create_run_dir("NVDA")
        rid = info["run_id"]
        # Three events.
        storage.append_run_event(rid, events.make_event(
            rid, "run_started", {"ticker": "NVDA"},
        ))
        storage.append_run_event(rid, events.make_event(
            rid, "analyst_started", {"node": "Market Analyst"},
        ))
        storage.append_run_event(rid, events.make_event(
            rid, "analyst_thinking", {"stage": "market", "message": "hi"},
        ))
        # In production the runner also emits analyst_completed for the
        # node (the build_health inference of "current node" relies on
        # the matched pair). Seed it so the done-run test sees no
        # in-flight node.
        storage.append_run_event(rid, events.make_event(
            rid, "analyst_completed",
            {"stage": "market", "summary": "completed", "node": "Market Analyst"},
        ))
        # A completed stage file.
        storage.write_stage(rid, "market", {
            "stage": "market",
            "node": "Market Analyst",
            "state_key": "market_report",
            "completed_at": "2026-06-04T12:00:01Z",
            "duration_ms": 1500,
            "value": "completed",
        })
        # An LLM call.
        llm_calls.save_llm_call(
            rid,
            node_name="Market Analyst",
            ticker="NVDA",
            model="gpt-4o-mini",
            prompt_text="price of NVDA?",
            response_text="NVDA is $500",
            input_tokens=10, output_tokens=20, total_tokens=30,
            duration_ms=400,
            started_at="2026-06-04T12:00:00.500Z",
        )
        return rid

    def test_trace_merges_events_stages_and_llm_calls(self, client, data_root):
        rid = self._seed_run(data_root)
        r = client.get(f"/api/runs/{rid}/trace")
        assert r.status_code == 200
        body = r.json()
        assert body["run_id"] == rid
        kinds = [it["kind"] for it in body["items"]]
        assert "event" in kinds
        assert "stage" in kinds
        assert "llm_call" in kinds
        # Sorted ascending by ts.
        ts_list = [it["ts"] for it in body["items"]]
        assert ts_list == sorted(ts_list), "items must be chronological"
        # Each item has a ts + kind.
        for it in body["items"]:
            assert "ts" in it
            assert "kind" in it

    def test_trace_kind_filter_excludes_other_kinds(self, client, data_root):
        rid = self._seed_run(data_root)
        r = client.get(f"/api/runs/{rid}/trace?kind=event")
        assert r.status_code == 200
        kinds = {it["kind"] for it in r.json()["items"]}
        assert kinds == {"event"}, f"expected only events, got {kinds}"

        r = client.get(f"/api/runs/{rid}/trace?kind=stage,llm_call")
        assert r.status_code == 200
        kinds = {it["kind"] for it in r.json()["items"]}
        assert kinds == {"stage", "llm_call"}

    def test_trace_kind_filter_validates_known_kinds(self, client, data_root):
        rid = self._seed_run(data_root)
        r = client.get(f"/api/runs/{rid}/trace?kind=event,nope")
        assert r.status_code == 400
        assert "nope" in r.json()["detail"]

    def test_trace_since_skips_items_with_older_or_equal_ts(self, client, data_root):
        rid = self._seed_run(data_root)
        # Use a ts that exactly matches the seeded LLM call (12:00:00.500Z).
        since = "2026-06-04T12:00:00.500Z"
        r = client.get(f"/api/runs/{rid}/trace?since={since}")
        assert r.status_code == 200
        items = r.json()["items"]
        # Nothing older than or equal to the since cutoff.
        assert all(it["ts"] > since for it in items), \
            f"expected all items > {since}, got {[it['ts'] for it in items]}"

    def test_trace_limit_caps_returned_items(self, client, data_root):
        rid = self._seed_run(data_root)
        r = client.get(f"/api/runs/{rid}/trace?limit=2")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        assert body["truncated"] is True
        assert len(body["items"]) == 2

    def test_trace_unknown_run_returns_404(self, client):
        r = client.get("/api/runs/NOPE:nope/trace")
        assert r.status_code == 404

    def test_health_running_run_reports_current_node_and_event_count(
        self, client, data_root,
    ):
        rid = self._seed_run(data_root)
        # Mark the run as still in flight.
        storage.mark_run_status(rid, status="running")
        r = client.get(f"/api/runs/{rid}/health")
        assert r.status_code == 200
        body = r.json()
        assert body["found"] is True
        assert body["status"] == "running"
        assert body["ticker"] == "NVDA"
        assert body["event_count"] == 4
        assert body["stages_completed"] == ["market"]
        assert body["llm_call_count"] == 1
        assert body["total_input_tokens"] == 10
        assert body["total_output_tokens"] == 20
        assert body["total_tokens"] == 30
        # The seeded run's analyst_started for Market Analyst has a
        # matching analyst_completed → no in-flight node. To exercise
        # the "current node" inference we strip the completion and
        # re-query.
        rd = storage.read_run_dir(rid)
        assert rd is not None
        ev_path = rd / "events.jsonl"
        import json as _json
        lines = ev_path.read_text(encoding="utf-8").splitlines()
        lines = [
            l for l in lines
            if _json.loads(l).get("type") != "analyst_completed"
        ]
        ev_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        r2 = client.get(f"/api/runs/{rid}/health").json()
        assert r2["current_node"] == "Market Analyst"
        # Just-seeded events are < 1 minute old ? not stale.
        assert body["is_stale"] is False
        # The "running" status with fresh events ? alive.
        assert body["is_alive"] is True
        # last_event summary has the most recent event.
        assert body["last_event"]["type"] == "analyst_completed"
        assert body["last_event"]["age_s"] is not None
        assert body["last_event"]["age_s"] >= 0
        # No subscribers on a fresh test client.
        assert body["subscribers"] == 0

    def test_health_done_run_is_alive_but_not_running(self, client, data_root):
        rid = self._seed_run(data_root)
        # Pin both started_at and finished_at to a fixed window so
        # duration_s is well-defined regardless of wall-clock time.
        storage.mark_run_status(
            rid, status="done",
            started_at="2026-06-04T12:00:00Z",
            finished_at="2026-06-04T12:00:30Z",
            decision_action="BUY", decision_target=500.0,
        )
        r = client.get(f"/api/runs/{rid}/health")
        body = r.json()
        assert body["status"] == "done"
        assert body["is_alive"] is True  # terminal → "alive" (observed)
        assert body["is_stale"] is False
        assert body["decision_action"] == "BUY"
        assert body["decision_target"] == 500.0
        assert body["duration_s"] is not None
        assert body["duration_s"] == 30.0
        # No in-flight nodes after done.
        assert body["current_node"] is None

    def test_health_stale_running_run_flips_is_stale(self, client, data_root):
        """A 'running' run whose last event is older than the staleness
        threshold is reported as stale so the UI can warn the user."""
        from datetime import datetime, timezone, timedelta
        rid = self._seed_run(data_root)
        # Backdate the run + last event to > 5 minutes ago.
        old_start = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        storage.mark_run_status(rid, started_at=old_start, status="running")
        # The seeded events are fresh from now(); re-emit one with a backdated ts.
        storage.append_run_event(rid, events.make_event(
            rid, "analyst_thinking", {"stage": "market", "message": "stale"},
        ))
        # Replace that line's ts on disk (write a new run_dir with a backdated event).
        rd = storage.read_run_dir(rid)
        assert rd is not None, "seeded run dir must exist"
        ev_path = rd / "events.jsonl"
        lines = ev_path.read_text(encoding="utf-8").splitlines()
        if lines:
            # Backdate the last event line.
            import json as _json
            last = _json.loads(lines[-1])
            last["ts"] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
            lines[-1] = _json.dumps(last)
            ev_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        r = client.get(f"/api/runs/{rid}/health")
        body = r.json()
        assert body["status"] == "running"
        assert body["is_stale"] is True
        # A stale "running" run is not considered alive (no recent
        # progress). is_stale and is_alive are intentionally separate
        # so a UI can show "stuck" vs "in progress but slow".
        assert body["is_alive"] is False

    def test_health_unknown_run_returns_404(self, client):
        r = client.get("/api/runs/NOPE:nope/health")
        assert r.status_code == 404

    def test_health_reflects_active_subscribers(self, client, data_root):
        """The health endpoint includes the live WS subscriber count
        so a UI can tell whether anyone is watching the run."""
        rid = self._seed_run(data_root)
        storage.mark_run_status(rid, status="running")

        from web.server import events as events_mod
        events_mod.reset_for_tests()
        events_mod._subscribers.setdefault(rid, set()).add("fake-ws-1")
        events_mod._subscribers.setdefault(rid, set()).add("fake-ws-2")

        r = client.get(f"/api/runs/{rid}/health")
        body = r.json()
        assert body["subscribers"] == 2
