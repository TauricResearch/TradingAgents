"""Auth flow: OTP request/verify (dev fallback), cookie session, me, logout."""
from __future__ import annotations


def test_request_otp_dev_fallback(client):
    r = client.post("/api/auth/request-otp", json={"email": "a@b.com"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_request_otp_rejects_unlisted(client):
    r = client.post("/api/auth/request-otp", json={"email": "stranger@x.com"})
    assert r.status_code == 403


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_verify_wrong_code_400(client):
    client.post("/api/auth/request-otp", json={"email": "a@b.com"})
    r = client.post("/api/auth/verify-otp", json={"email": "a@b.com", "code": "999999"})
    assert r.status_code == 400


def test_verify_sets_cookie_and_me_works(client, monkeypatch):
    import auth as _auth
    monkeypatch.setattr(_auth, "verify_otp", lambda email, code: True)
    r = client.post("/api/auth/verify-otp", json={"email": "a@b.com", "code": "000000"})
    assert r.status_code == 200
    assert r.json()["email"] == "a@b.com"
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "a@b.com"


def test_whitelist_file_no_restart(client, env):
    """A user added to the whitelist file is accepted immediately — the file
    is re-read on every request, so no app reload/restart is needed."""
    # Not in ALLOWED_EMAILS env (only a@b.com is) → rejected.
    assert client.post("/api/auth/request-otp",
                       json={"email": "fresh@x.com"}).status_code == 403

    # Append to ~/.tradingagents/allowed_emails.txt under the sandboxed HOME.
    wl = env / ".tradingagents" / "allowed_emails.txt"
    wl.parent.mkdir(parents=True, exist_ok=True)
    wl.write_text("# comment\nFresh@X.com\n", encoding="utf-8")

    # Same long-lived client/app — now accepted (case-insensitive), no restart.
    assert client.post("/api/auth/request-otp",
                       json={"email": "fresh@x.com"}).status_code == 200


def test_logout_clears_session(auth_client):
    assert auth_client.get("/api/auth/me").status_code == 200
    auth_client.post("/api/auth/logout")
    assert auth_client.get("/api/auth/me").status_code == 401
