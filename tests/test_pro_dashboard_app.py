"""Dashboard FastAPI endpoints (skipped without the dashboard extra)."""

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from tests.test_pro_pipeline_graph import CONFIG, FakePipelineLLM, pipeline_snapshot  # noqa: E402
from tradingagents.pro.dashboard.app import DashboardState, create_app  # noqa: E402
from tradingagents.pro.memory import ProMemory  # noqa: E402


@pytest.fixture()
def client():
    state = DashboardState(memory=ProMemory())
    state.recorder.record_run(
        FakePipelineLLM(), CONFIG, pipeline_snapshot(), memory=state.memory
    )
    return TestClient(create_app(state))


def test_index_serves_dashboard_html(client):
    # "/" serves the SPA when a frontend build exists, else the legacy page;
    # both carry the product name. The legacy page stays at /legacy.
    response = client.get("/")
    assert response.status_code == 200
    assert "TradingAgents Pro" in response.text
    legacy = client.get("/legacy")
    assert legacy.status_code == 200
    for section in ("overview", "recommendation", "timeline", "agents", "journal"):
        assert f'id="{section}"' in legacy.text


def test_index_quick_win_markers(client):
    """UX quick wins are wired into the legacy page (structural check)."""
    html = client.get("/legacy").text
    assert 'name="viewport"' in html                 # A11Y-02
    assert "@media (max-width: 900px)" in html       # A11Y-02
    assert "X-API-Key" in html                       # SEC-UI-01
    assert "STALE" in html and 'id="conn"' in html   # ALERT-01
    assert "dirGlyph" in html and "▲" in html        # A11Y-01
    assert "invalidation" in html                    # EXPL-02
    assert "document.hidden" in html                 # PERF-01
    assert 'id="haltBanner"' in html                 # RISK-01
    assert 'id="alerts"' in html                     # ALERT-02
    assert 'id="runSelector"' in html                # NAV-01
    assert "equityChart" in html                     # VIZ-01
    assert "counterarguments" in html                # EXPL-01


def test_api_surface(client):
    overview = client.get("/api/overview").json()
    assert overview["symbol"] == "XAUUSD"

    runs = client.get("/api/runs").json()
    assert len(runs) == 1 and runs[0]["action"] == "BUY"
    run_id = runs[0]["run_id"]

    timeline = client.get(f"/api/runs/{run_id}/timeline").json()
    assert any(e["speaker"] == "judge" for e in timeline["entries"])

    evidence = client.get(f"/api/runs/{run_id}/evidence").json()
    assert "technical" in evidence

    recommendation = client.get("/api/recommendation/latest").json()
    assert recommendation["action"] == "BUY" and "vote_breakdown" in recommendation
    assert "invalidation" in recommendation  # EXPL-02: reflection surfaced

    status = client.get("/api/status").json()
    # no router wired; arming absent = every pair paper (go-live Phase 4)
    assert status["attached"] is False
    assert status["trading_halted"] is None
    assert status["live_armed"] is False

    alerts = client.get("/api/alerts").json()
    assert alerts == {"alerts": []}  # clean accepted run

    for path in ("/api/journal", "/api/backtest", "/api/memory", "/api/agents"):
        assert client.get(path).status_code == 200


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/nope/timeline").status_code == 404


class TestRunPersistence:
    def test_round_trip_preserves_views(self, tmp_path):
        from tradingagents.pro.dashboard import service as views
        from tradingagents.pro.dashboard.recorder import PipelineRecorder

        memory = ProMemory()
        recorder = PipelineRecorder(store_dir=tmp_path)
        run = recorder.record_run(
            FakePipelineLLM(), CONFIG, pipeline_snapshot(), memory=memory
        )
        reloaded = PipelineRecorder(store_dir=tmp_path)
        assert [r.run_id for r in reloaded.runs] == [run.run_id]
        loaded = reloaded.runs[0]
        assert views.debate_timeline(loaded) == views.debate_timeline(run)
        assert views.evidence_panels(loaded) == views.evidence_panels(run)
        assert views.market_overview(loaded) == views.market_overview(run)
        assert loaded.recommendation.action == run.recommendation.action
        assert loaded.timeframe == "1d"

    def test_trigger_provenance_persists_and_defaults(self, tmp_path):
        """R3.2: runs carry who asked for them; pre-field files load 'loop'."""
        import json

        from tradingagents.pro.dashboard.recorder import PipelineRecorder

        memory = ProMemory()
        recorder = PipelineRecorder(store_dir=tmp_path)
        run = recorder.record_run(
            FakePipelineLLM(), CONFIG, pipeline_snapshot(), memory=memory,
            trigger="operator",
        )
        assert run.trigger == "operator"
        reloaded = PipelineRecorder(store_dir=tmp_path)
        assert reloaded.runs[0].trigger == "operator"
        # a pre-provenance file (no trigger key) loads as the schedule
        raw = json.loads((tmp_path / f"{run.run_id}.json").read_text())
        del raw["trigger"]
        (tmp_path / f"{run.run_id}.json").write_text(json.dumps(raw))
        legacy = PipelineRecorder(store_dir=tmp_path)
        assert legacy.runs[0].trigger == "loop"

    def test_pre_timing_file_loads_with_empty_node_times(self, tmp_path):
        """Runs persisted before node_times existed load fine (UI omits latency)."""
        import json

        from tradingagents.pro.dashboard.recorder import PipelineRecorder

        memory = ProMemory()
        recorder = PipelineRecorder(store_dir=tmp_path)
        run = recorder.record_run(
            FakePipelineLLM(), CONFIG, pipeline_snapshot(), memory=memory
        )
        assert run.node_times  # new runs record timings
        path = tmp_path / f"{run.run_id}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        del raw["node_times"]  # simulate a pre-R9 file
        path.write_text(json.dumps(raw), encoding="utf-8")
        loaded = PipelineRecorder(store_dir=tmp_path).runs[0]
        assert loaded.node_times == []
        assert loaded.node_sequence == run.node_sequence

    def test_corrupt_file_skipped(self, tmp_path):
        from tradingagents.pro.dashboard.recorder import PipelineRecorder

        (tmp_path / "bad.json").write_text("{nope", encoding="utf-8")
        recorder = PipelineRecorder(store_dir=tmp_path)
        assert recorder.runs == []

    def test_prune_beyond_cap(self, tmp_path):
        from tradingagents.pro.dashboard.recorder import PipelineRecorder

        memory = ProMemory()
        recorder = PipelineRecorder(max_runs=2, store_dir=tmp_path)
        for _ in range(3):
            recorder.record_run(FakePipelineLLM(), CONFIG, pipeline_snapshot(),
                                memory=memory)
        assert len(list(tmp_path.glob("*.json"))) == 2
        assert len(PipelineRecorder(max_runs=2, store_dir=tmp_path).runs) == 2

    def test_runs_rows_carry_timeframe(self, client):
        rows = client.get("/api/runs").json()
        assert rows[0]["timeframe"] == "1d"


class TestPipelineTriggerEndpoint:
    @pytest.fixture()
    def triggered_client(self):
        from tradingagents.pro.main import PipelineTrigger

        state = DashboardState(memory=ProMemory())

        # a stub trigger keeps this test free of execution wiring
        class StubTrigger(PipelineTrigger):
            def __init__(self):
                super().__init__(service=None)
                self.calls = []

            def run(self, symbol, timeframe):
                self.calls.append((symbol, timeframe))
                return {"ok": True}

        state.trigger = StubTrigger()
        return TestClient(create_app(state)), state.trigger

    def test_started(self, triggered_client):
        client, trigger = triggered_client
        response = client.post("/api/pipeline/run",
                               json={"symbol": "XAUUSD", "timeframe": "1h"})
        assert response.status_code == 202
        assert response.json()["status"] == "started"
        import time
        for _ in range(50):
            if trigger.calls:
                break
            time.sleep(0.02)
        assert trigger.calls == [("XAUUSD", "1h")]

    def test_validation(self, triggered_client):
        client, _ = triggered_client
        assert client.post("/api/pipeline/run",
                           json={"symbol": "DOGE", "timeframe": "1h"}).status_code == 422
        assert client.post("/api/pipeline/run",
                           json={"symbol": "XAUUSD", "timeframe": "5m"}).status_code == 422

    def test_busy_and_untriggered(self, triggered_client):
        client, trigger = triggered_client
        trigger._busy.acquire()
        try:
            assert client.post("/api/pipeline/run",
                               json={"symbol": "XAUUSD", "timeframe": "1h"}).status_code == 409
        finally:
            trigger._busy.release()
        bare = TestClient(create_app(DashboardState()))
        assert bare.post("/api/pipeline/run",
                         json={"symbol": "XAUUSD", "timeframe": "1h"}).status_code == 503


class TestMetricsEndpoint:
    def test_scrapeable_and_open(self, client):
        # no registry attached -> empty but 200 (scrape target always up)
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.text == ""

    def test_renders_registry(self):
        from tradingagents.pro.observability import MetricsRegistry

        state = DashboardState(memory=ProMemory())
        state.metrics = MetricsRegistry()
        state.metrics.inc("runs_total")
        text = TestClient(create_app(state)).get("/metrics").text
        assert "runs_total 1" in text
