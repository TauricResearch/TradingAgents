"""Regression coverage for secret-safe news provider degradation."""

from __future__ import annotations

import json

import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.news_key_health import NewsProviderKeyPool
from tradingagents.dataflows.tavily_news import (
    TavilyUnavailableError,
    clear_tavily_key_health,
    get_news_tavily,
)


class _Response:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def test_key_pool_rotates_around_only_the_throttled_key():
    clock = [10.0]
    pool = NewsProviderKeyPool("tavily", clock=lambda: clock[0])
    pool.configure(["first-secret", "second-secret"])

    assert pool.acquire() == "first-secret"
    pool.record_failure("first-secret", cooldown_seconds=60, reason="rate_limit")
    assert pool.acquire() == "second-secret"
    cooldown = pool.status()[0]
    assert cooldown.identifier
    assert "first-secret" not in repr(cooldown)
    assert "second-secret" not in repr(cooldown)

    clock[0] += 60
    assert pool.acquire() == "first-secret"


def test_tavily_rotates_keys_after_429_without_leaking_credentials(monkeypatch, tmp_path):
    requests_seen: list[str] = []

    def fake_post(_url, headers, json, timeout):
        del json
        assert timeout == 30
        authorization = headers["Authorization"]
        requests_seen.append(authorization)
        if authorization == "Bearer first-secret":
            return _Response(429, {"error": "rate limited"})
        return _Response(
            200,
            {
                "results": [{"title": "Official update", "url": "https://example.com/item"}],
                "request_id": "ok",
            },
        )

    clear_tavily_key_health()
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEYS", "first-secret, second-secret")
    monkeypatch.setattr("tradingagents.dataflows.tavily_news.requests.post", fake_post)
    set_config({"results_dir": str(tmp_path)})

    result = get_news_tavily("AAPL", "2026-01-01", "2026-01-02")

    assert result["items"][0]["title"] == "Official update"
    assert requests_seen == ["Bearer first-secret", "Bearer second-secret"]
    # A second request skips the still-cooling first key rather than poisoning
    # the whole provider or disclosing which credential was used.
    get_news_tavily("AAPL", "2026-01-01", "2026-01-02")
    assert requests_seen[-1] == "Bearer second-secret"


def test_tavily_403_is_explicit_and_does_not_rotate_to_another_key(monkeypatch, tmp_path):
    requests_seen: list[str] = []

    def fake_post(_url, headers, json, timeout):
        del json
        requests_seen.append(headers["Authorization"])
        return _Response(403, {"error": "forbidden"})

    clear_tavily_key_health()
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEYS", "first-secret, second-secret")
    monkeypatch.setattr("tradingagents.dataflows.tavily_news.requests.post", fake_post)
    set_config({"results_dir": str(tmp_path)})

    with pytest.raises(TavilyUnavailableError, match="HTTP 403") as exc_info:
        get_news_tavily("AAPL", "2026-01-01", "2026-01-02")

    assert requests_seen == ["Bearer first-secret"]
    assert "first-secret" not in str(exc_info.value)
    assert "second-secret" not in str(exc_info.value)


def test_a_share_news_uses_public_exchange_only_after_all_news_sources_fail(monkeypatch):
    calls: list[str] = []
    interface.clear_vendor_health()
    monkeypatch.setattr(interface, "get_vendor", lambda _category, method=None: "tavily,yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_news",
        {
            "tavily": lambda *_args, **_kwargs: calls.append("tavily") or "No news found for 002636.SZ",
            "yfinance": lambda *_args, **_kwargs: calls.append("yfinance") or "No news found for 002636.SZ",
            "china_exchange": lambda *_args, **_kwargs: calls.append("china_exchange") or {
                "source": "china_exchange",
                "items": [
                    {
                        "title": "董事会决议公告",
                        "url": "https://www.szse.cn/disclosure/example",
                        "published": "2026-01-02",
                        "publisher": "szse",
                    }
                ],
            },
        },
    )
    set_config({"a_share_news_official_fallback_enabled": True})

    result = interface.route_to_vendor("get_news", "002636.SZ", "2026-01-01", "2026-01-03")

    assert calls == ["tavily", "yfinance", "china_exchange"]
    assert "Sources used: china_exchange" in result
    assert "董事会决议公告" in result


def test_a_share_official_fallback_does_not_run_when_news_source_succeeds(monkeypatch):
    calls: list[str] = []
    interface.clear_vendor_health()
    monkeypatch.setattr(interface, "get_vendor", lambda _category, method=None: "tavily")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_news",
        {
            "tavily": lambda *_args, **_kwargs: calls.append("tavily") or {
                "source": "tavily",
                "items": [{"title": "Market news", "url": "https://example.com/item"}],
            },
            "china_exchange": lambda *_args, **_kwargs: calls.append("china_exchange") or {"items": []},
        },
    )
    set_config({"a_share_news_official_fallback_enabled": True})

    interface.route_to_vendor("get_news", "002636.SZ", "2026-01-01", "2026-01-03")

    assert calls == ["tavily"]
