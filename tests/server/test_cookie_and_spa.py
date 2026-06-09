"""Cookie Secure flag follows config (LAN/HTTP fix) + SPA is served at /."""
from __future__ import annotations


def _login_setcookie(client, monkeypatch):
    import auth as _auth
    monkeypatch.setattr(_auth, "verify_otp", lambda email, code: True)
    r = client.post("/api/auth/verify-otp", json={"email": "a@b.com", "code": "x"})
    assert r.status_code == 200
    return r.headers.get("set-cookie", "")


def test_cookie_not_secure_by_default(client, monkeypatch):
    # Default config (LAN/HTTP): cookie must NOT be Secure, else browsers drop it.
    import server.config as cfg
    monkeypatch.setattr(cfg.settings, "cookie_secure", False, raising=False)
    cookie = _login_setcookie(client, monkeypatch)
    assert "ta_session=" in cookie
    assert "Secure" not in cookie
    assert "HttpOnly" in cookie


def test_cookie_secure_when_enabled(client, monkeypatch):
    # HTTPS production opts in via TRADINGAGENTS_COOKIE_SECURE=1.
    import server.config as cfg
    monkeypatch.setattr(cfg.settings, "cookie_secure", True, raising=False)
    cookie = _login_setcookie(client, monkeypatch)
    assert "Secure" in cookie


def test_spa_index_served(client, monkeypatch, tmp_path):
    # When a built dist exists, "/" returns index.html.
    import server.config as cfg
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>TradingAgents</title>", encoding="utf-8")
    monkeypatch.setattr(cfg.settings, "frontend_dist", str(dist), raising=False)
    from fastapi.testclient import TestClient
    from server.app import create_app
    c = TestClient(create_app())
    r = c.get("/")
    assert r.status_code == 200
    assert "TradingAgents" in r.text
