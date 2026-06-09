"""Test fixtures: a TestClient with a sandboxed HOME and dev-fallback auth."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SESSION_SECRET", "test-secret-123")
    monkeypatch.setenv("ALLOWED_EMAILS", "a@b.com")
    monkeypatch.setenv("AUTH_DEV_FALLBACK", "1")
    monkeypatch.setenv("TRADINGAGENTS_COOKIE_SECURE", "0")
    return tmp_path


@pytest.fixture
def app(env):
    # Re-import to pick up env (auth reads env at call time, so a fresh app is fine).
    from server.app import create_app
    return create_app()


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def auth_client(client, monkeypatch):
    """A TestClient already carrying a valid session cookie for a@b.com."""
    import auth as _auth
    monkeypatch.setattr(_auth, "send_otp", lambda email: (True, "ok"))
    monkeypatch.setattr(_auth, "verify_otp", lambda email, code: True)
    r = client.post("/api/auth/verify-otp", json={"email": "a@b.com", "code": "000000"})
    assert r.status_code == 200, r.text
    return client
