import importlib

from fastapi.testclient import TestClient


def test_app_persists_run_history_across_store_reloads(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_WEB_DB", str(tmp_path / "app.sqlite3"))
    import tradingagents.webapi.app as app_module

    app_module = importlib.reload(app_module)
    client = TestClient(app_module.app)

    response = client.post(
        "/api/runs",
        json={
            "ticker": "NVDA",
            "analysts": ["market"],
            "use_mock_stream": True,
        },
    )
    response.raise_for_status()
    run_id = response.json()["run"]["id"]

    reloaded = importlib.reload(app_module)
    reloaded_client = TestClient(reloaded.app)

    runs = reloaded_client.get("/api/runs").json()["runs"]
    assert any(run["id"] == run_id and run["ticker"] == "NVDA" for run in runs)


def test_app_can_load_delete_and_export_run_history(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_WEB_DB", str(tmp_path / "app.sqlite3"))
    import tradingagents.webapi.app as app_module

    app_module = importlib.reload(app_module)
    client = TestClient(app_module.app)

    created = client.post(
        "/api/runs",
        json={
            "ticker": "NVDA",
            "company_name": "英伟达",
            "analysts": ["market"],
            "use_mock_stream": True,
        },
    ).json()["run"]

    run_id = created["id"]
    app_module.STORE.append_event(
        run_id,
        {
            "id": "evt_test",
            "runId": run_id,
            "type": "report",
            "agent": "Market Analyst",
            "status": "completed",
            "section": "market_report",
            "content": "### 市场分析师\n完整报告正文",
            "payload": {},
            "createdAt": created["created_at"],
        },
    )
    app_module.STORE.update_run(run_id, status="completed", decision="持有 / 观察")

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["run"]["company_name"] == "英伟达"
    assert detail["events"][0]["content"].endswith("完整报告正文")

    exported = client.get(f"/api/runs/{run_id}/export")
    exported.raise_for_status()
    assert "英伟达" in exported.text
    assert "持有 / 观察" in exported.text
    assert "完整报告正文" in exported.text

    deleted = client.delete(f"/api/runs/{run_id}")
    deleted.raise_for_status()
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_create_run_auto_fills_company_name(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_WEB_DB", str(tmp_path / "app.sqlite3"))
    import tradingagents.webapi.app as app_module

    app_module = importlib.reload(app_module)
    monkeypatch.setattr(
        app_module,
        "resolve_company_profile",
        lambda ticker: {"ticker": "NVDA", "company_name": "NVIDIA Corporation", "market": "NMS"},
    )
    client = TestClient(app_module.app)

    created = client.post(
        "/api/runs",
        json={
            "ticker": "NVDA",
            "analysts": ["market"],
            "use_mock_stream": True,
        },
    ).json()["run"]

    assert created["company_name"] == "NVIDIA Corporation"


def test_company_lookup_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_WEB_DB", str(tmp_path / "app.sqlite3"))
    import tradingagents.webapi.app as app_module

    app_module = importlib.reload(app_module)
    monkeypatch.setattr(
        app_module,
        "resolve_company_profile",
        lambda ticker: {"ticker": "NVDA", "company_name": "NVIDIA Corporation", "market": "NMS"},
    )
    client = TestClient(app_module.app)

    response = client.get("/api/companies/NVDA")

    assert response.json() == {"ticker": "NVDA", "company_name": "NVIDIA Corporation", "market": "NMS"}


def test_auth_login_and_logout_status(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_WEB_DB", str(tmp_path / "app.sqlite3"))
    import tradingagents.webapi.app as app_module

    app_module = importlib.reload(app_module)
    client = TestClient(app_module.app)

    assert client.get("/api/auth/status").json()["logged_in"] is False

    logged_in = client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).json()
    assert logged_in["logged_in"] is True
    assert logged_in["username"] == "admin"

    assert client.get("/api/auth/status").json()["logged_in"] is True
    assert client.post("/api/auth/logout").json()["logged_in"] is False
    assert client.get("/api/auth/status").json()["logged_in"] is False
