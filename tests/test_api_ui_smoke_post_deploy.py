from __future__ import annotations

import json
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
    assert 'href="/api-definition"' in html


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
