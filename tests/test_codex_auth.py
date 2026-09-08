"""Codex credential resolution from the official client's auth.json.

Two behaviours matter for not breaking the user's Codex login: refresh only
when the token is genuinely near expiry, and always persist the rotated refresh
token atomically (the refresh token rotates on every refresh, so refreshing
without persisting silently logs the user out of Codex).
"""
from __future__ import annotations

import base64
import json
import os
import stat
import time
from pathlib import Path

import pytest

from tradingagents.llm_clients import codex_auth


def _jwt(exp: float, aud: str = "app_TEST") -> str:
    """Build an unsigned JWT whose payload carries exp and aud."""
    def part(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{part({'alg': 'none'})}.{part({'exp': exp, 'aud': [aud]})}.sig"


def _auth_file(tmp_path: Path, exp_offset: float = 3600.0, **overrides) -> Path:
    payload = {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": {
            "id_token": _jwt(time.time() + exp_offset),
            "access_token": _jwt(time.time() + exp_offset),
            "refresh_token": "refresh-old",
            "account_id": "acct-123",
        },
        "last_refresh": "2026-07-20T05:33:55.696789Z",
    }
    payload.update(overrides)
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(payload))
    path.chmod(0o600)
    return path


def _fresh_tokens(**overrides) -> dict:
    payload = {
        "access_token": _jwt(time.time() + 864000),
        "refresh_token": "refresh-new",
        "id_token": _jwt(time.time() + 3600),
        "expires_in": 864000,
    }
    payload.update(overrides)
    return payload


@pytest.mark.unit
def test_valid_token_is_returned_without_refreshing(tmp_path, monkeypatch):
    path = _auth_file(tmp_path)
    before = path.read_text()

    def _explode(*args, **kwargs):
        raise AssertionError("refresh must not run for a healthy token")

    monkeypatch.setattr(codex_auth, "_refresh", _explode)
    creds = codex_auth.resolve(str(path))

    assert creds.account_id == "acct-123"
    assert creds.token == json.loads(before)["tokens"]["access_token"]
    assert path.read_text() == before


@pytest.mark.unit
def test_headers_carry_the_account_id():
    creds = codex_auth.CodexCredentials(token="t", account_id="acct-9")
    assert creds.headers["chatgpt-account-id"] == "acct-9"
    assert "Authorization" not in creds.headers


@pytest.mark.unit
@pytest.mark.parametrize("exp_offset", [-10.0, 60.0])
def test_expiring_token_is_refreshed_and_persisted(tmp_path, monkeypatch, exp_offset):
    path = _auth_file(tmp_path, exp_offset=exp_offset)
    calls = []
    fresh = _fresh_tokens()

    def _fake_refresh(refresh_token: str, client_id: str) -> dict:
        calls.append((refresh_token, client_id))
        return fresh

    monkeypatch.setattr(codex_auth, "_refresh", _fake_refresh)
    creds = codex_auth.resolve(str(path))

    assert calls == [("refresh-old", "app_TEST")]
    assert creds.token == fresh["access_token"]
    assert creds.account_id == "acct-123"

    written = json.loads(path.read_text())
    assert written["tokens"]["access_token"] == fresh["access_token"]
    assert written["tokens"]["refresh_token"] == "refresh-new"
    assert written["tokens"]["account_id"] == "acct-123"
    assert set(written) == {"auth_mode", "OPENAI_API_KEY", "tokens", "last_refresh"}
    assert written["auth_mode"] == "chatgpt"
    assert written["last_refresh"] != "2026-07-20T05:33:55.696789Z"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.unit
def test_write_back_is_atomic(tmp_path, monkeypatch):
    path = _auth_file(tmp_path, exp_offset=-10.0)
    monkeypatch.setattr(codex_auth, "_refresh", lambda *a, **k: _fresh_tokens())
    destinations = []
    real_replace = os.replace

    def _spy(src, dst):
        destinations.append(str(dst))
        real_replace(src, dst)

    monkeypatch.setattr(codex_auth.os, "replace", _spy)
    codex_auth.resolve(str(path))

    # A direct truncating write would never call os.replace.
    assert destinations == [str(path)]


@pytest.mark.unit
def test_refresh_failure_leaves_the_file_untouched(tmp_path, monkeypatch):
    path = _auth_file(tmp_path, exp_offset=-10.0)
    before = path.read_text()

    def _fail(*args, **kwargs):
        raise codex_auth.CodexAuthError("refresh rejected")

    monkeypatch.setattr(codex_auth, "_refresh", _fail)
    with pytest.raises(codex_auth.CodexAuthError):
        codex_auth.resolve(str(path))
    assert path.read_text() == before


@pytest.mark.unit
def test_missing_file_names_the_path_and_the_fix(tmp_path):
    missing = tmp_path / "nope.json"
    with pytest.raises(codex_auth.CodexAuthError, match="Sign in"):
        codex_auth.resolve(str(missing))


@pytest.mark.unit
def test_api_key_auth_mode_points_at_the_openai_provider(tmp_path):
    path = _auth_file(tmp_path, auth_mode="apikey")
    with pytest.raises(codex_auth.CodexAuthError, match="'openai' provider"):
        codex_auth.resolve(str(path))


@pytest.mark.unit
def test_missing_account_id_is_rejected(tmp_path):
    path = _auth_file(tmp_path)
    payload = json.loads(path.read_text())
    del payload["tokens"]["account_id"]
    path.write_text(json.dumps(payload))
    with pytest.raises(codex_auth.CodexAuthError, match="account"):
        codex_auth.resolve(str(path))


@pytest.mark.unit
def test_expired_token_without_refresh_token_is_rejected(tmp_path):
    path = _auth_file(tmp_path, exp_offset=-10.0)
    payload = json.loads(path.read_text())
    del payload["tokens"]["refresh_token"]
    path.write_text(json.dumps(payload))
    with pytest.raises(codex_auth.CodexAuthError, match="refresh token"):
        codex_auth.resolve(str(path))


@pytest.mark.unit
def test_client_id_falls_back_when_the_id_token_is_unreadable(tmp_path, monkeypatch):
    path = _auth_file(tmp_path, exp_offset=-10.0)
    payload = json.loads(path.read_text())
    payload["tokens"]["id_token"] = "not-a-jwt"
    path.write_text(json.dumps(payload))
    seen = []

    def _capture(refresh_token: str, client_id: str) -> dict:
        seen.append(client_id)
        return _fresh_tokens()

    monkeypatch.setattr(codex_auth, "_refresh", _capture)
    codex_auth.resolve(str(path))
    assert seen == [codex_auth.FALLBACK_CLIENT_ID]


def _degrading_reads(monkeypatch, path, drop: str):
    """Make the second read of the auth file return a file missing ``drop``.

    resolve() reads once to decide whether a refresh is needed, then re-reads
    under the lock. Nothing guarantees the two reads see the same file — the
    official Codex client can rewrite it in between.
    """
    intact = json.loads(path.read_text())
    degraded = json.loads(json.dumps(intact))
    del degraded["tokens"][drop]
    reads = iter([intact, degraded])
    monkeypatch.setattr(codex_auth, "_read_auth", lambda _path: next(reads))


@pytest.mark.unit
@pytest.mark.parametrize(
    "dropped,message", [("refresh_token", "refresh token"), ("account_id", "account")]
)
def test_file_degrading_under_the_lock_stays_actionable(
    tmp_path, monkeypatch, dropped, message
):
    path = _auth_file(tmp_path, exp_offset=-10.0)
    _degrading_reads(monkeypatch, path, dropped)
    monkeypatch.setattr(codex_auth, "_refresh", lambda *a, **k: _fresh_tokens())

    # Without re-validating after the second read this raises a bare KeyError,
    # which tells the user nothing about how to fix it.
    with pytest.raises(codex_auth.CodexAuthError, match=message):
        codex_auth.resolve(str(path))


@pytest.mark.unit
def test_env_var_selects_the_auth_path(tmp_path, monkeypatch):
    path = _auth_file(tmp_path)
    monkeypatch.setenv("TRADINGAGENTS_CODEX_AUTH_PATH", str(path))
    assert codex_auth.resolve().account_id == "acct-123"
