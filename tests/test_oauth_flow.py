"""Test dello scambio code->token (form-urlencoded, 5 campi)."""
from tradingagents.llm_clients.oauth import flow as flow_mod


def test_exchange_code_posts_form_urlencoded(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"id_token": "h.e.s", "access_token": "A", "refresh_token": "R"}

    def fake_post(url, data=None, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        return FakeResp()

    monkeypatch.setattr(flow_mod.httpx, "post", fake_post)
    tokens = flow_mod.exchange_code("THECODE", "VERIFIER")
    assert captured["url"] == flow_mod.OAUTH_TOKEN_URL
    assert captured["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    d = captured["data"]
    assert d["grant_type"] == "authorization_code"
    assert d["code"] == "THECODE"
    assert d["code_verifier"] == "VERIFIER"
    assert d["client_id"] == flow_mod.OAUTH_CLIENT_ID
    assert d["redirect_uri"] == "http://localhost:1455/auth/callback"
    assert set(d.keys()) == {"grant_type", "code", "redirect_uri", "client_id", "code_verifier"}
    assert tokens["access_token"] == "A"


def test_exchange_code_error_raises(monkeypatch):
    class FakeResp:
        status_code = 400

        def json(self):
            return {}

    monkeypatch.setattr(flow_mod.httpx, "post", lambda *a, **k: FakeResp())
    import pytest
    with pytest.raises(flow_mod.OAuthLoginError):
        flow_mod.exchange_code("c", "v")
