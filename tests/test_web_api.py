import os
from pathlib import Path

TEST_DB = Path("/tmp/tradingagents-web-test.db")
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["APP_SECRET_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"

from fastapi.testclient import TestClient

from backend.app import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_login_seeded_admin():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@local", "password": "admin123"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["user"]["role"] == "admin"


def test_analysis_requires_auth():
    with TestClient(app) as client:
        response = client.post("/api/v1/analysis", json={"symbol": "RELIANCE.NS"})
        assert response.status_code == 401


def test_stock_search():
    with TestClient(app) as client:
        response = client.get("/api/v1/stocks/search", params={"q": "TCS"})
        assert response.status_code == 200
        assert any(item["symbol"] == "TCS.NS" for item in response.json()["results"])


def test_watchlist_and_settings_roundtrip():
    with TestClient(app) as client:
        token = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@local", "password": "admin123"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        added = client.post("/api/v1/watchlist", json={"symbol": "INFY"}, headers=headers)
        assert added.status_code == 200
        listed = client.get("/api/v1/watchlist", headers=headers)
        assert listed.status_code == 200
        assert any(item["symbol"] == "INFY.NS" for item in listed.json()["items"])
        saved = client.put(
            "/api/v1/settings",
            json={"llm_provider": "openai", "research_depth": "shallow", "enable_news": False},
            headers=headers,
        )
        assert saved.status_code == 200
        assert saved.json()["research_depth"] == "shallow"
        assert saved.json()["enable_news"] is False
