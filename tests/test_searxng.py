"""Unit tests for the SearXNG news vendor."""

from unittest.mock import patch

import pytest
import requests

from tradingagents.dataflows import searxng
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows import config as config_module


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_company_name_cache():
    """Avoid cache bleed between tests (``_company_name`` is ``lru_cache``-d)."""
    searxng._company_name.cache_clear()
    yield
    searxng._company_name.cache_clear()


def _fake_response(payload, status_code=200):
    response = requests.Response()
    response.status_code = status_code
    response._content = (payload if isinstance(payload, bytes) else __import__("json").dumps(payload).encode())
    return response


@pytest.fixture
def stub_company_name():
    with patch.object(searxng, "_company_name", return_value="NVIDIA"):
        yield


def test_get_news_formats_results_and_dedupes(stub_company_name):
    payload = {
        "results": [
            {
                "title": "NVDA hits new high",
                "url": "https://news.example.com/a",
                "content": "Shares climbed after earnings.",
                "engine": "google news",
                "publishedDate": "2026-04-15T12:00:00Z",
            },
            {
                "title": "Duplicate URL should be dropped",
                "url": "https://news.example.com/a",
                "content": "different snippet",
                "engine": "bing news",
                "publishedDate": "2026-04-15T13:00:00Z",
            },
            {
                "title": "Reddit thread on NVDA",
                "url": "https://reddit.com/r/stocks/x",
                "content": "Retail sentiment piece.",
                "engine": "reddit",
                "publishedDate": None,
            },
        ]
    }

    with patch.object(searxng.requests, "get", return_value=_fake_response(payload)) as mocked:
        result = searxng.get_news_searxng("NVDA", "2026-04-01", "2026-04-30")

    assert mocked.called
    assert "## NVDA News, from 2026-04-01 to 2026-04-30" in result
    assert "NVDA hits new high" in result
    assert "Reddit thread on NVDA" in result
    assert "Duplicate URL should be dropped" not in result


def test_get_news_filters_outside_date_window(stub_company_name):
    payload = {
        "results": [
            {
                "title": "Too old",
                "url": "https://news.example.com/old",
                "content": "",
                "publishedDate": "2025-01-01T00:00:00Z",
            },
            {
                "title": "In window",
                "url": "https://news.example.com/in",
                "content": "",
                "publishedDate": "2026-04-15T00:00:00Z",
            },
        ]
    }

    with patch.object(searxng.requests, "get", return_value=_fake_response(payload)):
        result = searxng.get_news_searxng("NVDA", "2026-04-01", "2026-04-30")

    assert "In window" in result
    assert "Too old" not in result


def test_get_news_caps_results_at_limit(stub_company_name):
    payload = {
        "results": [
            {
                "title": f"Article {i}",
                "url": f"https://news.example.com/a{i}",
                "content": "",
                "publishedDate": "2026-04-15T00:00:00Z",
            }
            for i in range(40)
        ]
    }

    with patch.object(searxng.requests, "get", return_value=_fake_response(payload)):
        result = searxng.get_news_searxng(
            "NVDA", "2026-04-01", "2026-04-30", limit=5
        )

    assert result.count("### Article") == 5


def test_company_name_cached():
    """Caching means lookups for the same ticker only call yfinance once."""
    with patch.object(searxng.yf, "Ticker") as ticker_factory:
        ticker_factory.return_value.info = {"longName": "NVIDIA Corporation"}

        first = searxng._company_name("NVDA")
        second = searxng._company_name("NVDA")

    assert first == "NVIDIA Corporation"
    assert second == "NVIDIA Corporation"
    assert ticker_factory.call_count == 1


def test_searxng_request_failure_raises_unavailable(stub_company_name):
    with patch.object(
        searxng.requests,
        "get",
        side_effect=requests.ConnectionError("connection refused"),
    ):
        with pytest.raises(searxng.SearxngUnavailableError):
            searxng.get_news_searxng("NVDA", "2026-04-01", "2026-04-30")


def test_router_falls_back_when_searxng_unavailable():
    """``route_to_vendor`` should advance to yfinance when SearXNG is down."""
    from tradingagents.dataflows import interface

    config_module.set_config({"data_vendors": {"news_data": "searxng,yfinance"}})
    fallback_called = {"value": False}

    def _fake_yfinance(*_args, **_kwargs):
        fallback_called["value"] = True
        return "## yfinance fallback payload"

    original = interface.VENDOR_METHODS["get_news"]["yfinance"]
    interface.VENDOR_METHODS["get_news"]["yfinance"] = _fake_yfinance
    try:
        with patch.object(
            searxng.requests,
            "get",
            side_effect=requests.ConnectionError("connection refused"),
        ), patch.object(searxng, "_company_name", return_value="NVIDIA"):
            result = route_to_vendor("get_news", "NVDA", "2026-04-01", "2026-04-30")
    finally:
        interface.VENDOR_METHODS["get_news"]["yfinance"] = original
        config_module._config = None
        config_module.initialize_config()

    assert fallback_called["value"]
    assert result == "## yfinance fallback payload"
