"""Test dello store dei token OAuth: persistenza, scadenza da exp, refresh JSON."""
import base64
import json
import stat
import time

import pytest

from tradingagents.llm_clients.oauth import store as store_mod
from tradingagents.llm_clients.oauth.store import OAuthTokenStore, OAuthNotLoggedIn


def _jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.sig"


def _id_token(account_id="acct_123", fedramp=False, residency=None):
    auth = {"chatgpt_account_id": account_id, "chatgpt_account_is_fedramp": fedramp}
    if residency:
        auth["chatgpt_data_residency"] = residency
    return _jwt({"https://api.openai.com/auth": auth})


def _access_token(exp_offset=3600):
    return _jwt({"exp": int(time.time()) + exp_offset})


def _tokens(exp_offset=3600, **id_kwargs):
    return {
        "id_token": _id_token(**id_kwargs),
        "access_token": _access_token(exp_offset),
        "refresh_token": "REFRESH",
    }


def test_save_load_roundtrip_and_permissions(tmp_path):
    path = tmp_path / "oauth_openai.json"
    OAuthTokenStore(path=path).save(_tokens())
    loaded = OAuthTokenStore(path=path).load()
    assert loaded.access_token.startswith("eyJ") or "." in loaded.access_token
    assert loaded.refresh_token == "REFRESH"
    assert loaded.account_id == "acct_123"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_decode_account_fedramp_residency(tmp_path):
    path = tmp_path / "t.json"
    OAuthTokenStore(path=path).save(_tokens(account_id="acct_x", fedramp=True, residency="eu"))
    tok = OAuthTokenStore(path=path).load()
    assert tok.account_id == "acct_x"
    assert tok.is_fedramp is True
    assert tok.residency == "eu"


def test_load_missing_raises(tmp_path):
    with pytest.raises(OAuthNotLoggedIn):
        OAuthTokenStore(path=tmp_path / "nope.json").load()


def test_load_corrupt_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not json")
    with pytest.raises(OAuthNotLoggedIn):
        OAuthTokenStore(path=p).load()


def test_expiry_derives_from_access_token_exp(tmp_path):
    s = OAuthTokenStore(path=tmp_path / "t.json")
    s.save(_tokens(exp_offset=100))  # scade tra 100s
    tok = s.load()
    assert tok.is_expired(skew=300) is True   # entro lo skew -> da rinfrescare
    assert tok.is_expired(skew=10) is False


def test_refresh_uses_json_body_and_persists(tmp_path, monkeypatch):
    path = tmp_path / "t.json"
    s = OAuthTokenStore(path=path)
    s.save(_tokens(exp_offset=1))
    calls = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "id_token": _id_token(account_id="acct_123"),
                "access_token": _access_token(3600),
                "refresh_token": "REFRESH2",
            }

    def fake_post(url, json=None, data=None, headers=None, timeout=None):
        calls["url"] = url
        calls["json"] = json
        calls["data"] = data
        calls["headers"] = headers
        return FakeResp()

    monkeypatch.setattr(store_mod.httpx, "post", fake_post)
    new_tok = s.refresh()
    # body JSON (non form), 3 campi, senza scope
    assert calls["url"] == store_mod.OAUTH_TOKEN_URL
    assert calls["data"] is None
    assert calls["json"]["grant_type"] == "refresh_token"
    assert calls["json"]["refresh_token"] == "REFRESH"
    assert set(calls["json"].keys()) == {"client_id", "grant_type", "refresh_token"}
    # rotazione salvata
    assert new_tok.refresh_token == "REFRESH2"
    assert s.load().refresh_token == "REFRESH2"


def test_refresh_keeps_old_refresh_token_when_not_rotated(tmp_path, monkeypatch):
    s = OAuthTokenStore(path=tmp_path / "t.json")
    s.save(_tokens(exp_offset=1))

    class FakeResp:
        status_code = 200

        def json(self):
            return {"access_token": _access_token(3600)}  # niente refresh_token

    monkeypatch.setattr(store_mod.httpx, "post",
                        lambda *a, **k: FakeResp())
    tok = s.refresh()
    assert tok.refresh_token == "REFRESH"  # riusa il vecchio


def test_refresh_failure_raises(tmp_path, monkeypatch):
    s = OAuthTokenStore(path=tmp_path / "t.json")
    s.save(_tokens(exp_offset=1))

    class FakeResp:
        status_code = 400

        def json(self):
            return {}

    monkeypatch.setattr(store_mod.httpx, "post", lambda *a, **k: FakeResp())
    with pytest.raises(store_mod.OAuthRefreshFailed):
        s.refresh()


def test_default_store_path_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGAGENTS_OAUTH_PATH", str(tmp_path / "custom.json"))
    assert store_mod.default_store_path() == tmp_path / "custom.json"


def test_refresh_preserves_claims_when_id_token_absent(tmp_path, monkeypatch):
    # Se il refresh non rinvia id_token, account_id/fedramp/residency vengono
    # riderivati dall'id_token precedente (riusato), quindi sopravvivono.
    s = OAuthTokenStore(path=tmp_path / "t.json")
    s.save(_tokens(exp_offset=1, account_id="acct_keep", fedramp=True, residency="eu"))

    class FakeResp:
        status_code = 200

        def json(self):
            return {"access_token": _access_token(3600)}  # niente id_token

    monkeypatch.setattr(store_mod.httpx, "post", lambda *a, **k: FakeResp())
    tok = s.refresh()
    assert tok.account_id == "acct_keep"
    assert tok.is_fedramp is True
    assert tok.residency == "eu"


def test_refresh_permanent_error_code_in_message(tmp_path, monkeypatch):
    s = OAuthTokenStore(path=tmp_path / "t.json")
    s.save(_tokens(exp_offset=1))

    class FakeResp:
        status_code = 400

        def json(self):
            return {"error": {"code": "refresh_token_expired"}}

    monkeypatch.setattr(store_mod.httpx, "post", lambda *a, **k: FakeResp())
    with pytest.raises(store_mod.OAuthRefreshFailed) as exc:
        s.refresh()
    assert "refresh_token_expired" in str(exc.value)


def test_header_claims_reject_malformed_values():
    # Un account_id con caratteri non validi (es. newline/inietta header) -> None
    bad = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acct\r\nX-Inject: 1"}})
    assert store_mod.account_id_from_id_token(bad) is None
    good = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acct_123"}})
    assert store_mod.account_id_from_id_token(good) == "acct_123"


def test_save_uses_unique_tmp_even_if_path_ends_tmp(tmp_path):
    # Path che termina in .tmp non deve auto-collidere col file temporaneo.
    p = tmp_path / "store.tmp"
    s = OAuthTokenStore(path=p)
    s.save(_tokens())
    assert p.exists()
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    # nessun file .tmp residuo nella dir
    leftovers = [f for f in tmp_path.iterdir() if f.name.startswith(".oauth_")]
    assert leftovers == []
