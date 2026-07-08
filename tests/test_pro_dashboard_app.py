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
    response = client.get("/")
    assert response.status_code == 200
    assert "TradingAgents Pro" in response.text
    for section in ("overview", "recommendation", "timeline", "agents", "journal"):
        assert f'id="{section}"' in response.text


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

    for path in ("/api/journal", "/api/backtest", "/api/memory", "/api/agents"):
        assert client.get(path).status_code == 200


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/nope/timeline").status_code == 404
