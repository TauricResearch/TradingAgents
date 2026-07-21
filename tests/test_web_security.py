"""Security regressions: exact CSP header, foreign-Host rejection, config
whitelist exactness, key-echo canary, backend_url never echoed."""

import pytest
from fastapi.testclient import TestClient

from tradingagents.web.app import CONFIG_WHITELIST, create_app
from tradingagents.web.security import host_header_hostname

pytestmark = pytest.mark.unit

EXPECTED_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'"
)

CANARY = "sk-canary-value-should-never-leak"


async def scripted_engine(params, emit):
    emit("report_section", {"section": "market_report", "markdown": "# x"})
    return {"decision": "BUY"}


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tradingagents.web.settings._DEFAULT_PATH", tmp_path / "web_settings.json"
    )


@pytest.fixture
def client(tmp_path):
    app = create_app(engine=scripted_engine, results_dir=str(tmp_path / "results"))
    with TestClient(app, base_url="http://localhost") as client:
        yield client


def run_body(**overrides):
    body = {
        "ticker": "AAPL",
        "date": "2026-07-01",
        "analysts": ["market"],
        "provider": "openai",
        "deep_think_llm": "gpt-5.5",
        "quick_think_llm": "gpt-5.4-mini",
    }
    body.update(overrides)
    return body


def test_csp_header_exact_on_html_static_and_api(client):
    for path in ("/", "/api/health", "/api/providers"):
        response = client.get(path)
        assert response.headers["content-security-policy"] == EXPECTED_CSP, path
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "no-cache" in response.headers.get("cache-control", ""), path


def test_foreign_host_rejected(tmp_path):
    app = create_app(engine=scripted_engine, results_dir=str(tmp_path / "results"))
    # DNS-rebinding shape: attacker's hostname resolves to 127.0.0.1, but the
    # Host header still carries the foreign name.
    with TestClient(app, base_url="http://evil.example") as client:
        assert client.get("/api/health").status_code == 400
        assert client.post("/api/runs", json=run_body()).status_code == 400


@pytest.mark.parametrize("base_url", [
    "http://localhost", "http://127.0.0.1", "http://localhost:8035",
])
def test_local_hosts_allowed(tmp_path, base_url):
    app = create_app(engine=scripted_engine, results_dir=str(tmp_path / "results"))
    with TestClient(app, base_url=base_url) as client:
        assert client.get("/api/health").status_code == 200


def test_host_parsing_is_port_agnostic_and_ipv6_safe():
    assert host_header_hostname("localhost") == "localhost"
    assert host_header_hostname("LOCALHOST:9000") == "localhost"
    assert host_header_hostname("127.0.0.1:8035") == "127.0.0.1"
    assert host_header_hostname("[::1]:8035") == "::1"
    assert host_header_hostname("[::1]") == "::1"
    assert host_header_hostname("::1") == "::1"
    assert host_header_hostname("evil.example:8035") == "evil.example"
    assert host_header_hostname("") == ""


def test_config_whitelist_exactness(client):
    payload = client.get("/api/config").json()
    assert set(payload["config"].keys()) == set(CONFIG_WHITELIST)
    assert "backend_url" not in payload["config"]
    # The whitelist itself must never grow a secret-bearing key.
    for forbidden in ("backend_url", "api_key", "openai_api_key"):
        assert forbidden not in CONFIG_WHITELIST


def test_api_key_value_never_appears_in_any_response(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", CANARY)

    responses = [
        client.get("/api/health"),
        client.get("/api/providers"),
        client.get("/api/config"),
        client.get("/api/runs"),
        client.post("/api/runs", json=run_body()),
    ]
    run_id = responses[-1].json()["run_id"]
    for _ in range(100):
        state = client.get(f"/api/runs/{run_id}")
        if state.json()["state"] != "running":
            break
    responses.append(state)
    with client.stream("GET", f"/api/runs/{run_id}/events") as stream:
        sse_body = "".join(stream.iter_text())

    for response in responses:
        assert CANARY not in response.text
    assert CANARY not in sse_body


def test_backend_url_never_echoed(client):
    secret_url = "https://relay.example/v1?token=supersecret"
    response = client.post("/api/runs", json=run_body(
        provider="openai_compatible",
        backend_url=secret_url,
        deep_think_llm="local-model",
        quick_think_llm="local-model",
    ))
    assert response.status_code == 201
    assert "supersecret" not in response.text
    run_id = response.json()["run_id"]

    for _ in range(100):
        state = client.get(f"/api/runs/{run_id}")
        if state.json()["state"] != "running":
            break

    checks = [
        state,
        client.get("/api/config"),
        client.get("/api/runs"),
        client.get(f"/api/runs/{run_id}"),
    ]
    with client.stream("GET", f"/api/runs/{run_id}/events") as stream:
        sse_body = "".join(stream.iter_text())
    for response in checks:
        assert "supersecret" not in response.text
        assert "relay.example" not in response.text
    assert "supersecret" not in sse_body

    # And it must not be persisted to web settings either.
    payload = client.get("/api/config").json()
    assert "backend_url" not in payload["last_used"]


def test_no_cors_headers_ever(client):
    response = client.get(
        "/api/health", headers={"Origin": "http://localhost:5500"}
    )
    assert "access-control-allow-origin" not in response.headers
    preflight = client.request(
        "OPTIONS",
        "/api/runs",
        headers={
            "Origin": "http://localhost:5500",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in preflight.headers
