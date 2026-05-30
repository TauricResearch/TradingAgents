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


# --- binding del server di callback (port fallback) ------------------------
def test_bind_falls_back_to_1457_when_1455_busy(monkeypatch):
    seen = []

    def fake_httpserver(addr, handler):
        seen.append(addr[1])
        if addr[1] == 1455:
            raise OSError("address in use")
        return object()

    monkeypatch.setattr(flow_mod, "HTTPServer", fake_httpserver)
    server, port = flow_mod._bind_callback_server(object())
    assert port == 1457
    assert seen == [1455, 1457]


def test_bind_raises_when_both_ports_busy(monkeypatch):
    monkeypatch.setattr(flow_mod, "HTTPServer",
                        lambda addr, handler: (_ for _ in ()).throw(OSError("busy")))
    import pytest
    with pytest.raises(flow_mod.OAuthLoginError):
        flow_mod._bind_callback_server(object())


# --- login(): path di sicurezza --------------------------------------------
class _DummyServer:
    def server_close(self):
        pass


def _patch_login_env(monkeypatch, tmp_path, callback_result):
    from tradingagents.llm_clients.oauth.store import OAuthTokenStore
    monkeypatch.setattr(flow_mod, "generate_state", lambda: "FIXED_STATE")
    monkeypatch.setattr(flow_mod, "_bind_callback_server", lambda handler: (_DummyServer(), 1455))
    monkeypatch.setattr(flow_mod, "_collect_callback",
                        lambda server, result, timeout: result.update(callback_result))
    return OAuthTokenStore(path=tmp_path / "store.json")


def test_login_rejects_state_mismatch(monkeypatch, tmp_path):
    import pytest
    store = _patch_login_env(monkeypatch, tmp_path, {"state": "WRONG", "code": "c"})
    with pytest.raises(flow_mod.OAuthLoginError, match="CSRF|State|state"):
        flow_mod.login(open_browser=False, store=store)


def test_login_rejects_oauth_error_param(monkeypatch, tmp_path):
    import pytest
    store = _patch_login_env(monkeypatch, tmp_path, {"error": "access_denied"})
    with pytest.raises(flow_mod.OAuthLoginError):
        flow_mod.login(open_browser=False, store=store)


def test_login_rejects_missing_code(monkeypatch, tmp_path):
    import pytest
    store = _patch_login_env(monkeypatch, tmp_path, {"state": "FIXED_STATE"})  # niente code
    with pytest.raises(flow_mod.OAuthLoginError):
        flow_mod.login(open_browser=False, store=store)


def test_login_success_exchanges_and_saves(monkeypatch, tmp_path):
    import base64, json, time
    store = _patch_login_env(monkeypatch, tmp_path, {"state": "FIXED_STATE", "code": "GOODCODE"})

    def _jwt(p):
        h = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
        b = base64.urlsafe_b64encode(json.dumps(p).encode()).rstrip(b"=").decode()
        return f"{h}.{b}.s"

    captured = {}

    def fake_exchange(code, verifier, port=1455):
        captured["code"] = code
        return {"id_token": _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acct_ok"}}),
                "access_token": _jwt({"exp": int(time.time()) + 3600}),
                "refresh_token": "R"}

    monkeypatch.setattr(flow_mod, "exchange_code", fake_exchange)
    tokens = flow_mod.login(open_browser=False, store=store)
    assert captured["code"] == "GOODCODE"
    assert tokens.account_id == "acct_ok"
