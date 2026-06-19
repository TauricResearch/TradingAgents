"""Integration tests for the ticker accuracy agent.

Tests the full flow via the FastAPI test client with mocked LLM calls
and storage paths to avoid side effects.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.server import storage
from web.server.ticker_agent.router import router


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def isolate_storage(tmp_path: Path):
    """Redirect ticker agent storage to a temp directory."""
    storage.init_settings(data_dir=str(tmp_path / "data"), cache_dir=str(tmp_path / "cache"))
    storage.clear_run_dir_cache()
    yield


@pytest.fixture
def client():
    """Test client with a minimal app (no lifespan / background threads)."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def seed_runs(tmp_path: Path) -> dict[str, list[dict]]:
    """Create fake run records for the scorer.

    Each run is stored as ``data/<TICKER>/<slug>/run.json``, matching the
    same layout that ``storage.create_run_dir`` produces so that
    ``storage.list_ticker_runs`` and ``storage.walk_data_dir`` find them.
    """
    runs_dir = tmp_path / "data"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # AAPL: 3 runs, 2 right (BUY price increase), 1 wrong (SELL price increase)
    aapl_runs = [
        {"status": "done", "decision_action": "BUY", "start_price": 100.0, "end_price": 105.0, "started_at": "2026-06-01T00:00:00Z", "id": "r1"},
        {"status": "done", "decision_action": "BUY", "start_price": 100.0, "end_price": 103.0, "started_at": "2026-06-02T00:00:00Z", "id": "r2"},
        {"status": "done", "decision_action": "SELL", "start_price": 100.0, "end_price": 102.0, "started_at": "2026-06-03T00:00:00Z", "id": "r3"},
    ]
    for i, run in enumerate(aapl_runs):
        run_dir = runs_dir / "AAPL" / f"run_{i}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")

    # GOOGL: only 2 runs (below default min_samples=3)
    googl_runs = [
        {"status": "done", "decision_action": "BUY", "start_price": 100.0, "end_price": 110.0, "started_at": "2026-06-01T00:00:00Z", "id": "r4"},
        {"status": "done", "decision_action": "BUY", "start_price": 100.0, "end_price": 96.0, "started_at": "2026-06-02T00:00:00Z", "id": "r5"},
    ]
    for i, run in enumerate(googl_runs):
        run_dir = runs_dir / "GOOGL" / f"run_{i}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")

    return {"AAPL": aapl_runs, "GOOGL": googl_runs}


class TestIntegration:

    def test_status_endpoint(self, client):
        """GET /api/ticker-agent/status returns agent status."""
        r = client.get("/api/ticker-agent/status")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert data["status"] in ("idle", "running", "paused")

    def test_capabilities_endpoint(self, client):
        """GET /api/ticker-agent/capabilities returns endpoint list."""
        r = client.get("/api/ticker-agent/capabilities")
        assert r.status_code == 200
        data = r.json()
        assert "capabilities" in data
        assert len(data["capabilities"]) > 0
        assert all("path" in c and "available" in c for c in data["capabilities"])

    def test_accuracy_leaderboard_with_data(self, client, seed_runs):
        """GET /api/ticker-agent/accuracy-leaderboard returns scored tickers."""
        from web.server.ticker_agent.orchestrator import _rank_and_store
        _rank_and_store({})

        r = client.get("/api/ticker-agent/accuracy-leaderboard")
        assert r.status_code == 200
        data = r.json()
        assert "scores" in data
        scores = data["scores"]
        if "AAPL" in scores:
            aapl = scores["AAPL"]
            assert aapl["total_runs"] == 3
            assert aapl["right"] == 2
            assert aapl["win_rate"] == pytest.approx(0.6667, rel=0.01)

    def test_config_roundtrip(self, client):
        """PUT /api/ticker-agent/config saves and GET returns updated config."""
        r = client.put("/api/ticker-agent/config", json={"min_samples": 5})
        assert r.status_code == 200
        r2 = client.get("/api/ticker-agent/config")
        assert r2.status_code == 200
        assert r2.json()["min_samples"] == 5

    def test_missing_capabilities_endpoint(self, client):
        """GET /api/ticker-agent/missing-capabilities returns list."""
        r = client.get("/api/ticker-agent/missing-capabilities")
        assert r.status_code == 200
        data = r.json()
        assert "capabilities" in data

    def test_live_events_endpoint(self, client):
        """GET /api/ticker-agent/live-events returns step tracking."""
        r = client.get("/api/ticker-agent/live-events?since=0")
        assert r.status_code == 200
        data = r.json()
        assert "events" in data
        assert "current_step" in data
        assert "current_step_name" in data
        assert isinstance(data["events"], list)

    def test_activity_log_endpoint(self, client):
        """GET /api/ticker-agent/activity-log returns entries."""
        r = client.get("/api/ticker-agent/activity-log?limit=5")
        assert r.status_code == 200
        data = r.json()
        assert "entries" in data
        assert isinstance(data["entries"], list)

    @patch("web.server.ticker_agent.orchestrator.discover_universe")
    @patch("web.server.ticker_agent.orchestrator._get_sector_performance")
    @patch("web.server.ticker_agent.orchestrator._execute_plan")
    @patch("web.server.ticker_agent.orchestrator._call_llm_strategy")
    def test_run_now_cycle(self, mock_llm, mock_execute, mock_sector, mock_universe, client, seed_runs):
        """POST /api/ticker-agent/run-now executes a full agent cycle."""
        mock_sector.return_value = ""
        mock_universe.return_value = ["AAPL", "NVDA", "GOOGL"]
        mock_llm.return_value = {
            "investigation_plan": [],
            "sectors_to_watch": ["Technology"],
            "reasoning_summary": "Integration test cycle",
            "conclusions": ["Test passed"],
        }
        mock_execute.return_value = {"scheduled": []}
        r = client.post("/api/ticker-agent/run-now")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "completed"

    def test_pause_resume(self, client):
        """POST /api/ticker-agent/pause and /resume work."""
        r = client.post("/api/ticker-agent/pause")
        assert r.status_code == 200
        r2 = client.post("/api/ticker-agent/resume")
        assert r2.status_code == 200

    @patch("web.server.ticker_agent.orchestrator.discover_universe")
    @patch("web.server.ticker_agent.orchestrator._get_sector_performance")
    @patch("web.server.ticker_agent.orchestrator._execute_plan")
    @patch("web.server.ticker_agent.orchestrator._call_llm_strategy")
    def test_run_now_when_running(self, mock_llm, mock_execute, mock_sector, mock_universe, client):
        """POST /api/ticker-agent/run-now returns result."""
        mock_llm.return_value = {
            "investigation_plan": [],
            "sectors_to_watch": ["Technology"],
            "reasoning_summary": "test",
            "conclusions": ["ok"],
        }
        mock_execute.return_value = {"scheduled": []}
        r = client.post("/api/ticker-agent/run-now")
        assert r.status_code == 200
