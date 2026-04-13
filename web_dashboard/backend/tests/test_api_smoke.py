import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def _load_main_module(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(backend_dir))
    sys.modules.pop("main", None)
    return importlib.import_module("main")


def test_config_check_smoke(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    main = _load_main_module(monkeypatch)

    with TestClient(main.app) as client:
        response = client.get("/api/config/check")

    assert response.status_code == 200
    assert response.json() == {"configured": False}


def test_analysis_task_routes_smoke(monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    main = _load_main_module(monkeypatch)

    seeded_task = {
        "task_id": "task-smoke",
        "ticker": "AAPL",
        "date": "2026-04-11",
        "status": "running",
        "created_at": "2026-04-11T10:00:00",
    }

    with TestClient(main.app) as client:
        main.app.state.task_results["task-smoke"] = seeded_task

        health_response = client.get("/health")
        tasks_response = client.get("/api/analysis/tasks")
        status_response = client.get("/api/analysis/status/task-smoke")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert tasks_response.status_code == 200
    assert tasks_response.json()["total"] >= 1
    assert any(task["task_id"] == "task-smoke" for task in tasks_response.json()["tasks"])
    assert status_response.status_code == 200
    assert status_response.json()["task_id"] == "task-smoke"
