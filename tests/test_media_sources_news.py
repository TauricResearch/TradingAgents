"""Company-news queries avoid collisions from ambiguous short symbols."""

from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from tradingagents.dataflows import media_sources


def _rss(*titles):
    items = "".join(
        f"<item><guid>{i}</guid><title>{title}</title>"
        f"<link>https://news.google.com/articles/{i}</link>"
        "<pubDate>Wed, 22 Jul 2026 12:00:00 GMT</pubDate>"
        "<source url='https://www.reuters.com/world/'>Reuters</source>"
        "<description>summary</description></item>"
        for i, title in enumerate(titles)
    )
    channel = (
        "<title>Google News</title>"
        "<link>https://news.google.com/</link>"
        "<description>Google News feed</description>"
    )
    return BytesIO(f"<rss><channel>{channel}{items}</channel></rss>".encode())


@pytest.mark.unit
def test_public_provenance_url_drops_credential_bearing_query_and_fragment():
    secret = "must-not-be-persisted"

    normalized = media_sources.normalize_public_url(
        f"HTTPS://Example.COM:443/story?token={secret}&signature={secret}#fragment"
    )

    assert normalized == "https://example.com/story"
    assert secret not in normalized


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
def test_ticker_news_partial_transport_failure_is_not_observed_absence(monkeypatch):
    calls = 0

    def partial(_request, timeout):
        nonlocal calls
        del timeout
        calls += 1
        if calls == 1:
            raise OSError("temporary feed failure")
        return _rss("Observed company report")

    monkeypatch.setattr(media_sources, "urlopen", partial)
    monkeypatch.setattr(media_sources.time, "sleep", lambda _: None)

    with pytest.raises(media_sources.ProviderTransientError, match="incomplete"):
        media_sources.fetch_news("NVDA", now=1.0)


@pytest.mark.unit
def test_ticker_news_rejects_malformed_items_without_partial_salvage(monkeypatch):
    malformed = BytesIO(
        b"<rss><channel><title>News</title><link>https://example.com/</link>"
        b"<description>feed</description><item><guid>missing-fields</guid></item>"
        b"</channel></rss>"
    )
    responses = iter((malformed, _rss("Observed company report")))
    monkeypatch.setattr(
        media_sources, "urlopen", lambda _request, timeout: next(responses)
    )
    monkeypatch.setattr(media_sources.time, "sleep", lambda _: None)

    with pytest.raises(media_sources.ProviderResponseError, match="response contract"):
        media_sources.fetch_news("NVDA", now=1.0)


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
    assert {row["metadata"]["provider_external_id"] for row in rows} == {"0"}
    assert all(
        row["external_id"] == row["metadata"]["content_vintage_id"]
        for row in rows
    )


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
def test_top_news_ranked_feeds_cannot_silently_normalize_to_empty(monkeypatch):
    monkeypatch.setattr(media_sources, "urlopen", lambda request, timeout: _rss())

    with pytest.raises(
        media_sources.ProviderResponseError, match="response contract"
    ):
        media_sources.fetch_top_news_headlines()


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        b"<html><body>credential=must-not-log</body></html>",
        b"<rss><wrapper><channel /></wrapper></rss>",
        b"<rss><channel /></rss>",
        b"<rss />",
    ],
)
def test_google_news_rejects_well_formed_non_rss_channel_payloads(
    monkeypatch, caplog, payload,
):
    monkeypatch.setattr(
        media_sources,
        "urlopen",
        lambda request, timeout: BytesIO(payload),
    )

    with pytest.raises(RuntimeError, match="cursor was not advanced"):
        media_sources.fetch_global_news("global event", 1.0, "world")
    with pytest.raises(RuntimeError, match="response contract"):
        media_sources.fetch_top_news_headlines()

    assert "must-not-log" not in caplog.text
    assert "credential=" not in caplog.text


@pytest.mark.unit
def test_provider_response_reads_are_bounded_and_sanitized(monkeypatch, caplog):
    class InspectableResponse(BytesIO):
        def close(self):
            pass

    payload = InspectableResponse(b"x" * 65 + b"credential=must-not-log")
    monkeypatch.setattr(media_sources, "_MAX_PROVIDER_RESPONSE_BYTES", 64)
    monkeypatch.setattr(media_sources, "urlopen", lambda request, timeout: payload)

    with pytest.raises(media_sources.ProviderResponseError):
        media_sources._get_json(
            "https://api.x.com/2/test?q=credential%3Dmust-not-log",
            {"Accept": "application/json"},
            1.0,
        )

    assert payload.tell() == 65
    assert "must-not-log" not in caplog.text
    assert "credential=" not in caplog.text


@pytest.mark.unit
def test_global_news_keeps_raw_rows_and_persists_normalized_provenance(monkeypatch):
    payload = BytesIO(
        b"<rss><channel>"
        b"<title>Google News</title><link>https://news.google.com/</link>"
        b"<description>Google News feed</description>"
        b"<item><guid>release</guid><title>Acme launches product - PR Newswire</title>"
        b"<link>https://news.google.com/articles/release?utm_source=test&amp;b=2</link>"
        b"<pubDate>Wed, 22 Jul 2026 12:00:00 GMT</pubDate>"
        b"<source url='https://www.prnewswire.com/news/'>PR Newswire</source>"
        b"<description>company statement</description></item>"
        b"<item><guid>report</guid><title>Launch reshapes technology market - Reuters</title>"
        b"<link>HTTPS://NEWS.GOOGLE.COM:443/articles/report#fragment</link>"
        b"<pubDate>Wed, 22 Jul 2026 12:00:00 GMT</pubDate>"
        b"<source url='https://www.reuters.com/world/'>Reuters</source>"
        b"<description>independent report</description></item>"
        b"</channel></rss>"
    )
    monkeypatch.setattr(media_sources, "urlopen", lambda request, timeout: payload)

    rows = media_sources.fetch_global_news("technology launches", 1.0, "technology")

    assert len({row["external_id"] for row in rows}) == 2
    assert all(row["external_id"].startswith("google_news_v1_") for row in rows)
    assert rows[0]["metadata"] == {
        "article_url": "https://news.google.com/articles/release",
        "publisher_domain": "prnewswire.com",
        "provider_external_id": "release",
        "content_vintage_id": rows[0]["external_id"],
        "content_vintage_schema_version": 1,
    }
    assert rows[1]["metadata"] == {
        "article_url": "https://news.google.com/articles/report",
        "publisher_domain": "reuters.com",
        "provider_external_id": "report",
        "content_vintage_id": rows[1]["external_id"],
        "content_vintage_schema_version": 1,
    }


@pytest.mark.unit
def test_global_news_cluster_revisions_get_distinct_stable_content_vintages(monkeypatch):
    title = ["Original report - Reuters"]

    def response(_request, timeout):
        del timeout
        return _rss(title[0])

    monkeypatch.setattr(media_sources, "urlopen", response)

    original = media_sources.fetch_global_news("global policy", 1.0, "world")[0]
    repeated = media_sources.fetch_global_news("global policy", 2.0, "world")[0]
    title[0] = "Corrected report - Reuters"
    revised = media_sources.fetch_global_news("global policy", 3.0, "world")[0]

    assert original["external_id"] == repeated["external_id"]
    assert revised["external_id"] != original["external_id"]
    assert {
        original["metadata"]["provider_external_id"],
        revised["metadata"]["provider_external_id"],
    } == {"0"}


@pytest.mark.unit
def test_global_news_caps_each_broad_query_response(monkeypatch):
    monkeypatch.setattr(
        media_sources,
        "urlopen",
        lambda request, timeout: _rss(*(f"Global item {index}" for index in range(40))),
    )

    rows = media_sources.fetch_global_news("global policy", 1.0, "world", limit=25)

    assert len(rows) == 25
    assert len({row["external_id"] for row in rows}) == 25
    assert [
        row["metadata"]["provider_external_id"] for row in rows
    ] == [str(index) for index in range(25)]


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
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, media_sources.ProviderResponseError),
        (403, media_sources.ProviderResponseError),
        (404, media_sources.ProviderResponseError),
        (408, media_sources.ProviderTransientError),
        (429, media_sources.ProviderTransientError),
        (500, media_sources.ProviderTransientError),
        (503, media_sources.ProviderTransientError),
    ],
)
def test_global_news_http_status_retry_classification(monkeypatch, status, expected):
    monkeypatch.setattr(
        media_sources,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            HTTPError(
                "https://news.google.com/rss/search?q=must-not-log",
                status,
                "provider details must-not-log",
                {},
                None,
            )
        ),
    )

    with pytest.raises(expected):
        media_sources.fetch_global_news("global event", 1.0, "world")


@pytest.mark.unit
def test_global_news_explicit_empty_channel_remains_observed_absence(monkeypatch):
    monkeypatch.setattr(media_sources, "urlopen", lambda *_args, **_kwargs: _rss())

    assert media_sources.fetch_global_news("no matching event", 1.0, "world") == []


@pytest.mark.unit
def test_global_news_rejects_contentless_independent_editorial_item(monkeypatch):
    payload = BytesIO(
        b"<rss><channel><title>Google News</title>"
        b"<link>https://news.google.com/</link>"
        b"<description>Google News feed</description>"
        b"<item><guid>fieldless</guid>"
        b"<link>https://news.google.com/articles/fieldless</link>"
        b"<pubDate>Wed, 22 Jul 2026 12:00:00 GMT</pubDate>"
        b"<source url='https://www.reuters.com/world/'>Reuters</source>"
        b"</item></channel></rss>"
    )
    monkeypatch.setattr(media_sources, "urlopen", lambda *_args, **_kwargs: payload)

    with pytest.raises(media_sources.ProviderResponseError, match="item schema"):
        media_sources.fetch_global_news("global event", 1.0, "world")


@pytest.mark.unit
def test_global_news_rejects_nested_item_lookalikes(monkeypatch):
    payload = BytesIO(
        b"<rss><channel><title>Google News</title>"
        b"<link>https://news.google.com/</link>"
        b"<description>Google News feed</description>"
        b"<wrapper><item><guid>nested</guid></item></wrapper>"
        b"</channel></rss>"
    )
    monkeypatch.setattr(media_sources, "urlopen", lambda *_args, **_kwargs: payload)

    with pytest.raises(media_sources.ProviderResponseError, match="item structure"):
        media_sources.fetch_global_news("global event", 1.0, "world")


@pytest.mark.unit
def test_x_fetchers_fail_without_credentials_instead_of_recording_zero(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="bearer token"):
        media_sources.fetch_x_topic("trend_world", "global event", 1.0)
    with pytest.raises(RuntimeError, match="bearer token"):
        media_sources.fetch_x_trends(1)


@pytest.mark.unit
def test_x_fetchers_reject_provider_error_envelopes_without_leaking_details(
    monkeypatch, caplog,
):
    payload = {"errors": [{"detail": "credential=must-not-log"}]}
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(media_sources, "_get_json", lambda *args, **kwargs: payload)

    for fetch in (
        lambda: media_sources.fetch_x_topic(
            "trend_world", "global event", 1.0
        ),
        lambda: media_sources.fetch_x_trends(1),
    ):
        with pytest.raises(RuntimeError, match="response reported errors") as exc_info:
            fetch()
        assert "must-not-log" not in str(exc_info.value)
        assert "credential=" not in str(exc_info.value)

    assert "must-not-log" not in caplog.text
    assert "credential=" not in caplog.text


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"errors": {}},
        {"meta": []},
        {"meta": {"result_count": True}, "data": []},
        {"meta": {"result_count": 1}},
        {"meta": {"result_count": 1}, "data": []},
        {"data": "not-a-list"},
        {"data": ["not-an-object"]},
        {"data": [{}], "meta": {"result_count": 1}},
        {"data": [{"trend_name": "", "tweet_count": 1}]},
        {"data": [{"trend_name": "Event", "tweet_count": True}]},
    ],
)
def test_x_trends_rejects_malformed_response_envelopes(monkeypatch, payload):
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(
        media_sources, "_get_json", lambda *args, **kwargs: payload
    )

    with pytest.raises(RuntimeError, match="response"):
        media_sources.fetch_x_trends(1)


@pytest.mark.unit
def test_x_recent_search_rejects_malformed_includes(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(
        media_sources,
        "_get_json",
        lambda *args, **kwargs: {"data": [], "includes": []},
    )

    with pytest.raises(RuntimeError, match="response schema is invalid"):
        media_sources.fetch_x_topic("trend_world", "global event", 1.0)


@pytest.mark.unit
@pytest.mark.parametrize(
    "item",
    [
        {},
        {"id": "1", "author_id": "2", "created_at": "2026-07-22T12:00:00Z"},
        {
            "id": "1", "author_id": "2", "text": "reaction",
            "created_at": "2026-07-22T12:00:00",
        },
    ],
)
def test_x_recent_search_rejects_nonempty_malformed_items(monkeypatch, item):
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(
        media_sources,
        "_get_json",
        lambda *args, **kwargs: {
            "data": [item],
            "meta": {"result_count": 1},
            "includes": {"users": [{"id": "2", "username": "publicvoice"}]},
        },
    )

    with pytest.raises(media_sources.ProviderResponseError, match="item schema"):
        media_sources.fetch_x_topic("trend_world", "global event", 1.0)


@pytest.mark.unit
def test_x_explicit_zero_results_remain_observed_absence(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(
        media_sources,
        "_get_json",
        lambda *args, **kwargs: {"meta": {"result_count": 0}},
    )

    assert media_sources.fetch_x_topic(
        "trend_world", "global event", 1.0
    ) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        {"meta": {"result_count": 0}},
        {"data": [], "meta": {"result_count": 0}},
    ],
)
def test_x_trends_rejects_empty_ranked_response(monkeypatch, payload):
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(
        media_sources, "_get_json", lambda *args, **kwargs: payload
    )

    with pytest.raises(media_sources.ProviderResponseError, match="trend response"):
        media_sources.fetch_x_trends(1)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("parser", "value"),
    [
        (media_sources._iso_to_epoch, "2026-07-22T12:00:00"),
        (media_sources._rfc822_to_epoch, "Wed, 22 Jul 2026 12:00:00"),
    ],
)
def test_provider_dates_without_timezones_are_rejected(parser, value):
    assert parser(value) is None


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
