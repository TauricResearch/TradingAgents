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

    assert len(rows) == 8
    assert {row["category"] for row in rows} == {
        "general", "business", "technology", "world",
    }
    assert all("/rss/search" not in url for url in urls)
    assert all(row["rank"] == 0 for row in rows)
    assert {row["region"] for row in rows} == {"US", "GB", "IN", "SG", "AU"}


@pytest.mark.unit
def test_top_news_total_upstream_failure_is_not_observed_absence(
    monkeypatch, caplog,
):
    def unavailable(request, timeout):
        del request, timeout
        raise OSError("credential=must-not-log")

    monkeypatch.setattr(media_sources, "urlopen", unavailable)

    with pytest.raises(RuntimeError, match="absence was not observed"):
        media_sources.fetch_top_news_headlines()

    assert "must-not-log" not in caplog.text
    assert "credential=" not in caplog.text


@pytest.mark.unit
def test_top_news_partial_upstream_failure_fails_the_whole_discovery_slot(monkeypatch):
    calls = 0

    def partial(request, timeout):
        nonlocal calls
        del request, timeout
        calls += 1
        if calls < 8:
            raise OSError("unavailable")
        return _rss("Observed global event - Reuters")

    monkeypatch.setattr(media_sources, "urlopen", partial)

    with pytest.raises(RuntimeError, match="feed set was incomplete"):
        media_sources.fetch_top_news_headlines(limit_per_feed=1)


@pytest.mark.unit
def test_top_news_all_structurally_valid_empty_feeds_are_observed_absence(monkeypatch):
    monkeypatch.setattr(media_sources, "urlopen", lambda request, timeout: _rss())

    assert media_sources.fetch_top_news_headlines() == []


@pytest.mark.unit
def test_global_news_keeps_raw_rows_and_persists_normalized_provenance(monkeypatch):
    payload = BytesIO(
        b"<rss><channel>"
        b"<item><guid>release</guid><title>Acme launches product - PR Newswire</title>"
        b"<link>https://news.google.com/articles/release?utm_source=test&amp;b=2</link>"
        b"<source url='https://www.prnewswire.com/news/'>PR Newswire</source>"
        b"<description>company statement</description></item>"
        b"<item><guid>report</guid><title>Launch reshapes technology market - Reuters</title>"
        b"<link>HTTPS://NEWS.GOOGLE.COM:443/articles/report#fragment</link>"
        b"<source url='https://www.reuters.com/world/'>Reuters</source>"
        b"<description>independent report</description></item>"
        b"</channel></rss>"
    )
    monkeypatch.setattr(media_sources, "urlopen", lambda request, timeout: payload)

    rows = media_sources.fetch_global_news("technology launches", 1.0, "technology")

    assert [row["external_id"] for row in rows] == ["release", "report"]
    assert rows[0]["metadata"] == {
        "article_url": "https://news.google.com/articles/release?b=2",
        "publisher_domain": "prnewswire.com",
    }
    assert rows[1]["metadata"] == {
        "article_url": "https://news.google.com/articles/report",
        "publisher_domain": "reuters.com",
    }


@pytest.mark.unit
def test_global_news_caps_each_broad_query_response(monkeypatch):
    monkeypatch.setattr(
        media_sources,
        "urlopen",
        lambda request, timeout: _rss(*(f"Global item {index}" for index in range(40))),
    )

    rows = media_sources.fetch_global_news("global policy", 1.0, "world", limit=25)

    assert len(rows) == 25
    assert [row["external_id"] for row in rows] == [str(index) for index in range(25)]


@pytest.mark.unit
def test_global_news_transport_failure_is_not_reported_as_observed_absence(
    monkeypatch, caplog,
):
    sensitive_query = "global policy credential=must-not-log"

    def fail(_request, *, timeout):
        del timeout
        raise OSError("provider details must-not-log")

    monkeypatch.setattr(media_sources, "urlopen", fail)

    with pytest.raises(RuntimeError, match="cursor was not advanced"):
        media_sources.fetch_global_news(sensitive_query, 1.0, "world")

    assert sensitive_query not in caplog.text
    assert "must-not-log" not in caplog.text


@pytest.mark.unit
def test_x_fetchers_fail_without_credentials_instead_of_recording_zero(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="bearer token"):
        media_sources.fetch_x_topic("trend_world", "global event", 1.0)
    with pytest.raises(RuntimeError, match="bearer token"):
        media_sources.fetch_x_trends(1)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("publisher", "title"),
    [
        ("OpenAI", "Introducing GPT-X - OpenAI"),
        ("Tesla", "We, Robot - Tesla"),
        ("Acme Newsroom", "Acme publishes an update - Acme Newsroom"),
    ],
)
def test_company_authored_detection_catches_first_party_launch_language(publisher, title):
    assert media_sources.looks_company_authored(publisher, title)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("publisher", "title"),
    [
        ("Reuters", "OpenAI introduces GPT-X - Reuters"),
        ("Reuters", "Reuters examines a new model - Reuters"),
        ("The Verge", "Introducing the newest AI model - The Verge"),
        ("Robotics News", "We, Robot revisited - Robotics News"),
        ("AI", "Retail demand rises - AI"),
    ],
)
def test_company_authored_detection_preserves_independent_editorial_coverage(
    publisher, title
):
    assert not media_sources.looks_company_authored(publisher, title)


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
