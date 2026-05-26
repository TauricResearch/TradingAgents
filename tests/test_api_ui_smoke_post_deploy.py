from __future__ import annotations

import json
import time
import urllib.request
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest


BASE_URL = "http://localhost:9000"


def _get_text(path: str) -> str:
    with urlopen(f"{BASE_URL}{path}") as resp:
        return resp.read().decode("utf-8", errors="replace")


def _get_json(path: str, params: dict | None = None) -> dict:
    query = f"?{urlencode(params)}" if params else ""
    with urlopen(f"{BASE_URL}{path}{query}") as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


@pytest.mark.smoke
def test_ui_contains_all_navigation_links() -> None:
    html = _get_text("/ui")
    assert 'href="/ui"' in html
    assert 'href="/batching"' in html
    assert 'href="/completed"' in html
    assert 'href="/requests/closed?format=html"' in html
    assert 'href="/settings"' in html


@pytest.mark.smoke
def test_linked_pages_are_reachable() -> None:
    for path in ("/batching", "/settings", "/completed", "/requests/closed?format=html"):
        html = _get_text(path)
        assert "<html" in html.lower()


@pytest.mark.smoke
def test_batching_page_contains_history_popup_elements() -> None:
    html = _get_text("/batching")
    assert "historyModal" in html
    assert "showRecommendationHistory" in html
    assert "/batching/history/" in html


@pytest.mark.smoke
def test_batching_history_endpoint_returns_shape() -> None:
    payload = _get_json("/batching/history/NVDA", {"provider": "google", "limit": 5})
    assert payload.get("ticker") == "NVDA"
    assert "history" in payload
    assert isinstance(payload["history"], list)


@pytest.mark.smoke
def test_metrics_today_endpoint_returns_shape() -> None:
    payload = _get_json("/metrics/llm-calls/today")
    assert "date_utc" in payload
    assert "total_llm_calls" in payload
    assert "providers" in payload
    assert "roles" in payload
    assert isinstance(payload["providers"], list)
    assert isinstance(payload["roles"], list)


@pytest.mark.smoke
def test_latest_recommendation_endpoint_returns_shape() -> None:
    payload = _get_json("/recommendations/latest/NVDA")
    assert payload.get("ticker") == "NVDA"
    assert "available" in payload
    assert "latest" in payload


# ---------------------------------------------------------------------------
# Env-var SET + GET round-trip tests
# Values are read from the local .env file so no secrets are hardcoded here.
# ---------------------------------------------------------------------------

def _load_env_file(path: str = "../.env") -> dict[str, str]:
    """Parse KEY=VALUE lines from a .env file and return a dict."""
    import os
    env_path = os.path.join(os.path.dirname(__file__), path)
    result: dict[str, str] = {}
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                result[key.strip()] = val.strip()
    except FileNotFoundError:
        pass
    return result


def _put_env_var(var_name: str, value: str) -> dict:
    """PUT /env/{var_name} with JSON body {"value": value}."""
    url = f"{BASE_URL}/env/{var_name}"
    data = json.dumps({"value": value}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PUT",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


@pytest.mark.smoke
@pytest.mark.parametrize("var_name", ["GOOGLE_API_KEY", "OPENROUTER_API_KEY"])
def test_env_set_and_get_roundtrip(var_name: str) -> None:
    """SET a key via PUT /env/{var_name}, wait 5 s, then verify GET returns same value."""
    local_env = _load_env_file()
    expected_value = local_env.get(var_name, "")

    # SET
    put_resp = _put_env_var(var_name, expected_value)
    assert put_resp.get("name") == var_name, f"PUT response name mismatch: {put_resp}"
    assert put_resp.get("exists") is True, f"PUT response exists != True: {put_resp}"

    # Wait for any async persistence to settle
    time.sleep(5)

    # GET and verify
    get_resp = _get_json(f"/env/{var_name}")
    assert get_resp.get("name") == var_name, f"GET response name mismatch: {get_resp}"
    assert get_resp.get("exists") is True, f"GET reports key does not exist: {get_resp}"
    assert get_resp.get("value") == expected_value, (
        f"Value mismatch for {var_name}: "
        f"expected={expected_value!r} got={get_resp.get('value')!r}"
    )
