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


def test_index_quick_win_markers(client):
    """UX quick wins are wired into the page (structural check)."""
    html = client.get("/").text
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
    assert status == {"attached": False, "trading_halted": None}  # no router wired

    alerts = client.get("/api/alerts").json()
    assert alerts == {"alerts": []}  # clean accepted run

    for path in ("/api/journal", "/api/backtest", "/api/memory", "/api/agents"):
        assert client.get(path).status_code == 200


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/nope/timeline").status_code == 404
