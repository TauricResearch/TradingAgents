"""Company-news queries avoid collisions from ambiguous short symbols."""

from io import BytesIO
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from tradingagents.dataflows import media_sources


def _rss(*titles):
    items = "".join(
        f"<item><guid>{i}</guid><title>{title}</title>"
        "<pubDate>Wed, 22 Jul 2026 12:00:00 GMT</pubDate>"
        "<description>summary</description></item>"
        for i, title in enumerate(titles)
    )
    return BytesIO(f"<rss><channel>{items}</channel></rss>".encode())


@pytest.mark.unit
def test_ambiguous_ticker_uses_company_identity_and_filters_mismatch(monkeypatch):
    urls = []

    def fake_urlopen(request, timeout):
        urls.append(request.full_url)
        if "finance.yahoo.com" in request.full_url:
            return _rss("Citigroup reports quarterly results")
        return _rss("Alphabet C stock rises", "Citi raises its outlook")

    monkeypatch.setattr(media_sources, "urlopen", fake_urlopen)
    monkeypatch.setattr(media_sources.time, "sleep", lambda _: None)

    rows = media_sources.fetch_news("c", now=1.0)

    assert [row["title"] for row in rows] == [
        "Citigroup reports quarterly results",
        "Citi raises its outlook",
    ]
    google_query = parse_qs(urlparse(urls[1]).query)["q"][0]
    assert "Citigroup" in unquote(google_query)


@pytest.mark.unit
def test_unambiguous_ticker_keeps_symbol_anchored_query(monkeypatch):
    urls = []

    def fake_urlopen(request, timeout):
        urls.append(request.full_url)
        return _rss()

    monkeypatch.setattr(media_sources, "urlopen", fake_urlopen)
    monkeypatch.setattr(media_sources.time, "sleep", lambda _: None)

    media_sources.fetch_news("NVDA", now=1.0)

    assert "NVDA" in parse_qs(urlparse(urls[1]).query)["q"][0]


@pytest.mark.unit
def test_top_news_discovery_uses_ranked_feeds_without_search_queries(monkeypatch):
    urls = []

    def fake_urlopen(request, timeout):
        urls.append(request.full_url)
        return _rss("A major current event - Reuters")

    monkeypatch.setattr(media_sources, "urlopen", fake_urlopen)

    rows = media_sources.fetch_top_news_headlines(limit_per_feed=1)

    assert len(rows) == 4
    assert {row["category"] for row in rows} == {
        "general", "business", "technology", "world",
    }
    assert all("/rss/search" not in url for url in urls)
    assert all(row["rank"] == 0 for row in rows)


@pytest.mark.unit
def test_global_news_rejects_company_authored_releases(monkeypatch):
    payload = BytesIO(
        b"<rss><channel>"
        b"<item><guid>release</guid><title>Acme launches product - PR Newswire</title>"
        b"<source>PR Newswire</source><description>company statement</description></item>"
        b"<item><guid>report</guid><title>Launch reshapes technology market - Reuters</title>"
        b"<source>Reuters</source><description>independent report</description></item>"
        b"</channel></rss>"
    )
    monkeypatch.setattr(media_sources, "urlopen", lambda request, timeout: payload)

    rows = media_sources.fetch_global_news("technology launches", 1.0, "technology")

    assert [row["external_id"] for row in rows] == ["report"]


@pytest.mark.unit
def test_x_trends_uses_bearer_and_returns_normalized_records(monkeypatch):
    captured = {}

    def fake_get_json(url, headers, timeout):
        captured.update(url=url, headers=headers)
        return {"data": [{"trend_name": "Major Event", "tweet_count": 1234}]}

    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")
    monkeypatch.setattr(media_sources, "_get_json", fake_get_json)

    rows = media_sources.fetch_x_trends(woeid=1, limit=30)

    assert rows == [{"name": "Major Event", "tweet_count": 1234}]
    assert "/trends/by/woeid/1" in captured["url"]
    assert parse_qs(urlparse(captured["url"]).query)["max_trends"] == ["30"]
    assert captured["headers"]["Authorization"] == "Bearer test-token"
