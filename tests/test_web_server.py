import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
import web.server as srv
from web.server import app


@pytest.fixture
def client(tmp_path):
    settings_file = tmp_path / "web_config.json"
    srv.SETTINGS_PATH = settings_file
    yield TestClient(app)
    srv.SETTINGS_PATH = srv._DEFAULT_SETTINGS_PATH


def test_get_settings_returns_defaults_when_no_file(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "llm_provider" in data
    assert "research_depth" in data


def test_post_settings_saves_and_echoes(client, tmp_path):
    payload = {"llm_provider": "anthropic", "research_depth": 3}
    resp = client.post("/api/settings", json=payload)
    assert resp.status_code == 200
    assert resp.json()["llm_provider"] == "anthropic"


def test_post_analyze_returns_409_when_already_running(client):
    srv._analysis_running = True
    try:
        resp = client.post("/api/analyze", json={"ticker": "NVDA", "date": "2024-05-10"})
        assert resp.status_code == 409
    finally:
        srv._analysis_running = False


def test_post_stop_clears_flag(client):
    srv._analysis_running = True
    resp = client.post("/api/stop")
    assert resp.status_code == 200
    assert not srv._analysis_running
