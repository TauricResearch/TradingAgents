from datetime import datetime

import pytest

from tradingagents.dataflows import interface, newsdata_io
from tradingagents.dataflows.errors import NoMarketDataError


def _article(title, published, *, article_id="id", sentiment=None):
    return {
        "article_id": article_id,
        "title": title,
        "description": f"Description for {title}",
        "pubDate": published,
        "source_name": "Example News",
        "link": "https://example.com/article",
        "sentiment": sentiment,
    }


@pytest.mark.unit
def test_newsdata_is_registered_for_news_tools():
    assert interface.VENDOR_METHODS["get_news"]["newsdata"] is newsdata_io.get_news
    assert interface.VENDOR_METHODS["get_global_news"]["newsdata"] is newsdata_io.get_global_news


@pytest.mark.unit
def test_missing_key_is_typed_not_configured(monkeypatch):
    monkeypatch.delenv("NEWSDATA_API_KEY", raising=False)
    with pytest.raises(newsdata_io.NewsDataNotConfiguredError):
        newsdata_io._api_key()


@pytest.mark.unit
def test_ticker_news_uses_symbol_and_filters_window(monkeypatch):
    seen = {}

    def fake_request(params):
        seen.update(params)
        return {
            "status": "success",
            "results": [
                _article(
                    "IN WINDOW",
                    "2026-09-26 12:00:00",
                    article_id="1",
                    sentiment="positive",
                ),
                _article("FUTURE", "2026-10-01 12:00:00", article_id="2"),
            ],
        }

    monkeypatch.setattr(newsdata_io, "_request", fake_request)
    monkeypatch.setattr(newsdata_io, "get_config", lambda: {"news_article_limit": 5})
    out = newsdata_io.get_news("TSLA", "2026-09-20", "2026-09-27")

    assert seen["q"] == "TSLA"
    assert "from_date" not in seen
    assert "to_date" not in seen
    assert "IN WINDOW" in out and "FUTURE" not in out
    assert "Vendor sentiment: positive" in out
    assert "Coverage note:" in out


@pytest.mark.unit
def test_global_news_uses_configured_defaults(monkeypatch):
    seen = {}

    def fake_request(params):
        seen.update(params)
        return {
            "status": "success",
            "results": [_article("MARKETS", "2026-09-25 10:00:00")],
        }

    monkeypatch.setattr(newsdata_io, "_request", fake_request)
    monkeypatch.setattr(
        newsdata_io,
        "get_config",
        lambda: {"global_news_lookback_days": 7, "global_news_article_limit": 3},
    )
    out = newsdata_io.get_global_news("2026-09-27")

    assert "from_date" not in seen
    assert "to_date" not in seen
    assert "MARKETS" in out


@pytest.mark.unit
def test_out_of_window_feed_is_no_data_not_current_news(monkeypatch):
    monkeypatch.setattr(
        newsdata_io,
        "_request",
        lambda params: {
            "status": "success",
            "results": [
                _article("CURRENT", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            ],
        },
    )
    monkeypatch.setattr(newsdata_io, "get_config", lambda: {"news_article_limit": 5})

    with pytest.raises(NoMarketDataError) as exc:
        newsdata_io.get_news("TSLA", "2020-01-01", "2020-01-07")
    assert "CURRENT" not in str(exc.value)
    assert "not an absence" in str(exc.value)
