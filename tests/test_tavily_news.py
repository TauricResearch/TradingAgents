import json

from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.tavily_news import get_news_tavily


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def test_tavily_news_uses_budget_defaults_and_logs_raw_response(monkeypatch, tmp_path):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "results": [
                    {
                        "title": "Apple earnings preview",
                        "url": "https://example.com/apple",
                        "content": "Apple earnings are in focus.",
                        "score": 0.91,
                    }
                ],
                "usage": {"credits": 1},
                "request_id": "req-123",
            }
        )

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr("tradingagents.dataflows.tavily_news.requests.post", fake_post)
    set_config(
        {
            "results_dir": str(tmp_path),
            "tavily_search_depth": "basic",
            "tavily_max_results": 5,
            "tavily_topic": "finance",
            "tavily_include_raw_content": "false",
            "tavily_include_answer": False,
            "tavily_include_images": False,
            "tavily_auto_parameters": "false",
        }
    )

    result = get_news_tavily("AAPL", "2026-01-01", "2026-01-31")

    assert captured["json"]["search_depth"] == "basic"
    assert captured["json"]["max_results"] == 5
    assert captured["json"]["topic"] == "finance"
    assert captured["json"]["include_raw_content"] is False
    assert captured["json"]["include_answer"] is False
    assert captured["json"]["include_images"] is False
    assert captured["json"]["auto_parameters"] is False
    assert result["items"][0]["source"] == "tavily"

    raw_files = list((tmp_path / "AAPL" / "2026-01-31" / "data").glob("tavily_get_news_*.json"))
    assert len(raw_files) == 1
    saved = json.loads(raw_files[0].read_text(encoding="utf-8"))
    assert saved["usage"] == {"credits": 1}
    assert saved["request_id"] == "req-123"


def test_news_aggregation_curates_and_deduplicates_sources(monkeypatch):
    monkeypatch.setattr(
        interface,
        "get_vendor",
        lambda category, method=None: "tavily,yfinance,alpha_vantage",
    )
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_news",
        {
            "tavily": lambda *args, **kwargs: {
                "source": "tavily",
                "items": [
                    {
                        "title": "Apple earnings preview",
                        "url": "https://example.com/apple",
                        "content": "Tavily summary.",
                        "published": "2026-01-30",
                        "source": "tavily",
                    }
                ],
            },
            "yfinance": lambda *args, **kwargs: (
                "## AAPL News\n\n"
                "### Apple earnings preview (source: Yahoo Finance)\n"
                "Duplicate summary.\n"
                "Link: https://example.com/apple\n\n"
                "### Apple supplier update (source: Yahoo Finance)\n"
                "Supplier summary.\n"
                "Link: https://example.com/supplier\n"
            ),
            "alpha_vantage": lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("alpha unavailable")
            ),
        },
    )
    set_config({"news_curator_max_items": 10})

    result = interface.route_to_vendor("get_news", "AAPL", "2026-01-01", "2026-01-31")

    assert "Curated News Package" in result
    assert "Sources used: tavily, yfinance" in result
    assert result.count("Apple earnings preview") == 1
    assert "Apple supplier update" in result
    assert "alpha_vantage: alpha unavailable" in result


def test_news_aggregation_returns_readable_missing_status(monkeypatch):
    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "tavily,yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_news",
        {
            "tavily": lambda *args, **kwargs: {"source": "tavily", "items": []},
            "yfinance": lambda *args, **kwargs: "No news found for AAPL",
        },
    )

    result = interface.route_to_vendor("get_news", "AAPL", "2026-01-01", "2026-01-31")

    assert "No curated news found" in result
    assert "Tavily returned no results" in result
    assert "No news found for AAPL" in result


def test_news_aggregation_treats_error_strings_as_source_failures(monkeypatch):
    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "default")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_news",
        {
            "tavily": lambda *args, **kwargs: {
                "source": "tavily",
                "items": [
                    {
                        "title": "Apple AI investment",
                        "url": "https://example.com/apple-ai",
                        "content": "Tavily summary.",
                    }
                ],
            },
            "yfinance": lambda *args, **kwargs: "Error fetching news for AAPL: rate limited",
            "alpha_vantage": lambda *args, **kwargs: "No news found for AAPL",
        },
    )

    result = interface.route_to_vendor("get_news", "AAPL", "2026-01-01", "2026-01-31")

    assert "Sources used: tavily" in result
    assert "yfinance: Error fetching news for AAPL: rate limited" in result
    assert "alpha_vantage: No news found for AAPL" in result
    assert "source: yfinance" not in result
