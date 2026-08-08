"""Dynamic X discovery stays broad, diverse, and tightly bounded."""

import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from tradingagents import poller
from tradingagents.dataflows import media_sources
from tradingagents.dataflows.media_sources import _row
from tradingagents.dataflows.media_store import SqliteMediaStore

_X_WINDOW_OPEN_UTC = datetime(2026, 8, 5, 21, tzinfo=timezone.utc).timestamp()
_X_WINDOW_CLOSED_UTC = datetime(2026, 8, 5, 23, 46, tzinfo=timezone.utc).timestamp()


@pytest.mark.unit
def test_x_topic_query_is_public_relevant_and_minimum_sized(monkeypatch):
    captured = {}

    def fake_get_json(url, headers, timeout):
        captured.update(url=url, headers=headers, timeout=timeout)
        return {
            "data": [{
                "id": "post-1",
                "author_id": "101",
                "created_at": "2026-07-22T12:00:00Z",
                "text": "People react to a major story",
                "public_metrics": {
                    "like_count": 2, "reply_count": 0,
                    "repost_count": 1, "quote_count": 0,
                },
            }],
            "includes": {"users": [{
                "id": "101", "username": "publicvoice", "verified_type": "none",
                "name": "Alice Example", "description": "Watching world events",
                "parody": False, "is_identity_verified": False,
                "url": "https://alice.example/profile?token=private#fragment",
                "entities": {"url": {"urls": [{
                    "expanded_url": (
                        "https://alice.example/about?api_key=private#fragment"
                    ),
                }]}},
                "created_at": "2020-01-01T00:00:00Z",
                "public_metrics": {
                    "followers_count": 100, "following_count": 20,
                    "post_count": 500,
                },
            }]},
        }

    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(media_sources, "_get_json", fake_get_json)

    rows = media_sources.fetch_x_topic(
        "trend_world", '"Bordeaux" wildfires', 1_800_000_000.0, limit=3
    )

    params = parse_qs(urlparse(captured["url"]).query)
    assert params["max_results"] == ["10"]
    assert params["sort_order"] == ["relevancy"]
    assert "Bordeaux" in params["query"][0]
    assert "-is:retweet -is:reply" in params["query"][0]
    assert "from:" not in params["query"][0]
    assert "$" not in params["query"][0]
    assert "post.fields" in params
    assert "tweet.fields" not in params
    assert {
        "description", "entities", "is_identity_verified",
        "name", "parody", "url",
    }.issubset(set(params["user.fields"][0].split(",")))
    assert "affiliation" not in params["user.fields"][0].split(",")
    assert captured["headers"]["Authorization"] == "Bearer secret-test-token"
    assert rows[0]["ticker"] == "@TREND_WORLD"
    assert rows[0]["metadata"]["evidence_role"] == "unverified_public_reaction"
    assert rows[0]["metadata"]["author_id"] == "101"
    assert rows[0]["metadata"]["automation_signals_complete"] is True
    assert rows[0]["metadata"]["profile_screening_complete"] is True
    assert rows[0]["metadata"]["organization_signals"] == []
    assert rows[0]["metadata"]["author_display_name"] == "Alice Example"
    assert rows[0]["metadata"]["author_description"] == "Watching world events"
    assert rows[0]["metadata"]["author_profile_url"] == (
        "https://alice.example/profile"
    )
    assert rows[0]["metadata"]["author_profile_entity_urls"] == [
        "https://alice.example/about"
    ]
    assert "private" not in json.dumps(rows[0]["metadata"])
    assert rows[0]["metadata"]["account_created_utc"] is not None
    assert rows[0]["metadata"]["engagement"]["retweet_count"] == 1
    assert "repost_count" not in rows[0]["metadata"]["engagement"]
    assert rows[0]["metadata"]["author_metrics"]["tweet_count"] == 500
    assert "post_count" not in rows[0]["metadata"]["author_metrics"]
    assert 0 <= rows[0]["metadata"]["automation_risk"] <= 1


@pytest.mark.unit
def test_x_topic_accepts_expanded_user_without_a_bio(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(
        media_sources,
        "_get_json",
        lambda *_args, **_kwargs: {
            "data": [{
                "id": "no-bio-post",
                "author_id": "303",
                "created_at": "2026-07-22T12:00:00Z",
                "text": "A substantive public reaction",
                "public_metrics": {
                    "like_count": 1,
                    "reply_count": 0,
                    "retweet_count": 0,
                    "quote_count": 0,
                },
            }],
            "includes": {"users": [{
                "id": "303",
                "username": "quiet_observer",
                "name": "Alice Example",
                "parody": False,
                "is_identity_verified": False,
                "verified_type": "none",
                "created_at": "2020-01-01T00:00:00Z",
                "public_metrics": {
                    "followers_count": 100,
                    "following_count": 20,
                    "tweet_count": 500,
                },
            }]},
        },
    )

    rows = media_sources.fetch_x_topic(
        "trend_world", "major event", 1_800_000_000.0
    )

    assert [row["external_id"] for row in rows] == ["no-bio-post"]
    assert rows[0]["metadata"]["author_description"] == ""
    assert rows[0]["metadata"]["profile_screening_complete"] is True


@pytest.mark.unit
def test_x_topic_excludes_an_author_with_incomplete_optional_screening(
    monkeypatch,
):
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(
        media_sources,
        "_get_json",
        lambda *_args, **_kwargs: {
            "data": [{
                "id": "unscreenable-post",
                "author_id": "404",
                "created_at": "2026-07-22T12:00:00Z",
                "text": "A substantive public reaction",
                "public_metrics": {
                    "like_count": 1,
                    "reply_count": 0,
                    "repost_count": 0,
                    "quote_count": 0,
                },
            }],
            "includes": {"users": [{
                "id": "404",
                "username": "unscreenable_user",
                "name": "Alice Example",
                "is_identity_verified": False,
                "verified_type": "none",
                "created_at": "2020-01-01T00:00:00Z",
                "public_metrics": {
                    "followers_count": 100,
                    "following_count": 20,
                    "post_count": 500,
                },
            }]},
        },
    )

    assert media_sources.fetch_x_topic(
        "trend_world", "major event", 1_800_000_000.0
    ) == []


@pytest.mark.unit
def test_x_metric_aliases_must_be_unambiguous():
    aliases = media_sources.GLOBAL_X_ADAPTER_POLICY["recent_search"][
        "response_metric_aliases"
    ]["post"]

    with pytest.raises(media_sources.ProviderResponseError, match="metrics schema"):
        media_sources._normalize_x_metrics(
            {
                "like_count": 1,
                "reply_count": 0,
                "retweet_count": 2,
                "repost_count": 2,
                "quote_count": 0,
            },
            aliases,
        )


@pytest.mark.unit
def test_x_topic_excludes_official_business_accounts(monkeypatch):
    excluded_type = media_sources.GLOBAL_X_ADAPTER_POLICY["recent_search"][
        "excluded_verified_types"
    ][0]

    def fake_get_json(url, headers, timeout):
        return {
            "data": [
                {
                    "id": "company-post", "author_id": "1", "text": "Announcement",
                    "created_at": "2026-07-22T12:00:00Z",
                    "public_metrics": {
                        "like_count": 1, "reply_count": 0,
                        "retweet_count": 0, "quote_count": 0,
                    },
                },
                {
                    "id": "person-post", "author_id": "2", "text": "My reaction",
                    "created_at": "2026-07-22T12:00:00Z",
                    "public_metrics": {
                        "like_count": 1, "reply_count": 0,
                        "retweet_count": 0, "quote_count": 0,
                    },
                },
                {
                    "id": "unverified-company-post", "author_id": "3",
                    "text": "Our product announcement",
                    "created_at": "2026-07-22T12:00:00Z",
                    "public_metrics": {
                        "like_count": 1, "reply_count": 0,
                        "retweet_count": 0, "quote_count": 0,
                    },
                },
            ],
            "includes": {"users": [
                {
                    "id": "1", "username": "officialco",
                    "verified_type": excluded_type,
                    "name": "Acme Products", "description": "",
                    "parody": False, "is_identity_verified": True,
                    "created_at": "2020-01-01T00:00:00Z",
                    "public_metrics": {
                        "followers_count": 100, "following_count": 20,
                        "tweet_count": 500,
                    },
                },
                {
                    "id": "2", "username": "publicvoice", "verified_type": "none",
                    "name": "Alice Example", "description": "Watching world events",
                    "parody": False, "is_identity_verified": False,
                    "created_at": "2020-01-01T00:00:00Z",
                    "public_metrics": {
                        "followers_count": 100, "following_count": 20,
                        "tweet_count": 500,
                    },
                },
                {
                    "id": "3", "username": "acme_updates", "verified_type": "none",
                    "name": "Acme", "description": "Official company account",
                    "parody": False, "is_identity_verified": False,
                    "created_at": "2020-01-01T00:00:00Z",
                    "public_metrics": {
                        "followers_count": 100, "following_count": 20,
                        "tweet_count": 500,
                    },
                },
            ]},
        }

    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(media_sources, "_get_json", fake_get_json)

    rows = media_sources.fetch_x_topic("trend_world", "major event", 123.0)

    assert [row["external_id"] for row in rows] == ["person-post"]
    assert rows[0]["author"] == "publicvoice"


@pytest.mark.unit
def test_x_ineligible_author_does_not_discard_valid_sibling(monkeypatch):
    def fake_get_json(url, headers, timeout):
        return {
            "data": [
                {
                    "id": "ineligible-post", "author_id": "202",
                    "text": "A substantive public reaction",
                    "created_at": "2026-07-22T12:00:00Z",
                    "public_metrics": {
                        "like_count": 1, "reply_count": 0,
                        "retweet_count": 0, "quote_count": 0,
                    },
                },
                {
                    "id": "valid-post", "author_id": "203",
                    "text": "Another substantive public reaction",
                    "created_at": "2026-07-22T12:00:00Z",
                    "public_metrics": {
                        "like_count": 1, "reply_count": 0,
                        "retweet_count": 0, "quote_count": 0,
                    },
                },
            ],
            "includes": {"users": [
                {
                    "id": "202", "username": "incomplete_user",
                    "verified_type": "none",
                    "name": "Alice Example",
                    "description": "Watching world events",
                    "parody": False, "is_identity_verified": False,
                    "public_metrics": {
                        "followers_count": 100, "following_count": 20,
                        "tweet_count": 500,
                    },
                },
                {
                    "id": "203", "username": "public_user",
                    "verified_type": "none",
                    "name": "Bob Example",
                    "description": "Watching world events",
                    "parody": False, "is_identity_verified": False,
                    "created_at": "2020-01-01T00:00:00Z",
                    "public_metrics": {
                        "followers_count": 100, "following_count": 20,
                        "tweet_count": 500,
                    },
                },
            ]},
        }

    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(media_sources, "_get_json", fake_get_json)

    rows = media_sources.fetch_x_topic(
        "trend_world", "major event", 1_800_000_000.0
    )

    assert [row["external_id"] for row in rows] == ["valid-post"]


@pytest.mark.unit
@pytest.mark.parametrize("verified_type", [None, "unknown-tier"])
def test_x_unknown_verified_type_excludes_author(
    monkeypatch, verified_type,
):
    user = {
        "id": "202",
        "username": "public_user",
        "name": "Alice Example",
        "description": "Watching world events",
        "parody": False,
        "is_identity_verified": False,
        "created_at": "2020-01-01T00:00:00Z",
        "public_metrics": {
            "followers_count": 100,
            "following_count": 20,
            "tweet_count": 500,
        },
    }
    if verified_type is not None:
        user["verified_type"] = verified_type
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(
        media_sources,
        "_get_json",
        lambda *_args, **_kwargs: {
            "data": [{
                "id": "post",
                "author_id": "202",
                "text": "A substantive public reaction",
                "created_at": "2026-07-22T12:00:00Z",
                "public_metrics": {
                    "like_count": 1,
                    "reply_count": 0,
                    "retweet_count": 0,
                    "quote_count": 0,
                },
            }],
            "includes": {"users": [user]},
        },
    )

    assert media_sources.fetch_x_topic(
        "trend_world", "major event", 1_800_000_000.0
    ) == []


@pytest.mark.unit
def test_x_profile_screen_is_complete_and_conservative():
    policy = media_sources.GLOBAL_X_ADAPTER_POLICY["recent_search"]
    person = {
        "username": "alice_example",
        "name": "Alice Example",
        "description": "Watching world events",
        "parody": False,
        "is_identity_verified": False,
    }
    assert media_sources._x_author_profile(person, policy)[
        "organization_signals"
    ] == []

    incomplete = dict(person)
    incomplete.pop("parody")
    with pytest.raises(
        media_sources.ProviderResponseError, match="author profile"
    ):
        media_sources._x_author_profile(incomplete, policy)

    invalid_description = {**person, "description": None}
    with pytest.raises(
        media_sources.ProviderResponseError, match="author profile"
    ):
        media_sources._x_author_profile(invalid_description, policy)

    organization = {**person, "username": "acme_corp"}
    assert media_sources._x_author_profile(organization, policy)[
        "organization_signals"
    ] == ["username_organization_language"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "profile_fields",
    [
        {"url": "javascript:alert(1)"},
        {"entities": {"url": {"urls": [{"expanded_url": {"bad": "url"}}]}}},
    ],
)
def test_x_author_profile_rejects_malformed_present_urls(profile_fields):
    policy = media_sources.GLOBAL_X_ADAPTER_POLICY["recent_search"]
    person = {
        "username": "alice_example",
        "name": "Alice Example",
        "description": "Watching world events",
        "parody": False,
        "is_identity_verified": False,
        **profile_fields,
    }

    with pytest.raises(
        media_sources.ProviderResponseError, match="profile URL"
    ):
        media_sources._x_author_profile(person, policy)


@pytest.mark.unit
def test_discovery_selects_current_news_across_three_categories(monkeypatch):
    headlines = [
        {"external_id": "w1", "title": "Wildfires force Bordeaux evacuations - Reuters",
         "body": "", "created_utc": 10.0, "publisher": "Reuters", "category": "world", "rank": 0},
        {"external_id": "b1", "title": "Central banks surprise global markets - Bloomberg",
         "body": "", "created_utc": 11.0, "publisher": "Bloomberg", "category": "business", "rank": 0},
        {"external_id": "t1", "title": "Helios Labs releases Nova model - The Verge",
         "body": "", "created_utc": 12.0, "publisher": "The Verge", "category": "technology", "rank": 2},
        {"external_id": "t0", "title": "Helios Labs product review - Helios Labs",
         "body": "", "created_utc": 13.0, "publisher": "Helios Labs", "category": "technology", "rank": 0},
        # Cross-feed presence raises this story's information score.
        {"external_id": "t1", "title": "Helios Labs releases Nova model - The Verge",
         "body": "", "created_utc": 12.0, "publisher": "The Verge", "category": "general", "rank": 1},
    ]
    feed_limits = []

    def fetch_headlines(*, limit_per_feed):
        feed_limits.append(limit_per_feed)
        return headlines

    monkeypatch.setattr(poller, "fetch_top_news_headlines", fetch_headlines)
    monkeypatch.setattr(
        poller, "fetch_x_trends",
        lambda woeid, **_kwargs: (
            [{"name": "Helios Labs", "tweet_count": 1000}] if woeid == 1 else []
        ),
    )

    topics = poller.discover_x_topics(max_topics=3)

    assert [topic["category"] for topic in topics] == ["world", "business", "technology"]
    assert all(topic["query"] for topic in topics)
    assert topics[2]["query"].startswith('"Helios Labs"')
    assert {topic["external_id"] for topic in topics} == {"w1", "b1", "t1"}
    assert feed_limits == [12]


@pytest.mark.unit
def test_discovery_normalization_matching_and_query_contract():
    assert poller._semantic_terms(
        "Nova AI models launch worldwide - Reuters"
    ) == {"nova", "ai", "model", "launch", "world"}
    assert poller._same_story(
        "Nova AI model launches worldwide - Reuters",
        "Nova AI models launched around world - BBC",
    ) is True
    assert poller._trend_matches_headline(
        "#OpenAI GPT6", "OpenAI launches GPT6 model"
    ) is True
    assert poller._trend_matches_headline(
        "#OpenAI Markets", "OpenAI launches model"
    ) is False
    assert poller._headline_query(
        "Breaking OpenAI GPT-6 Model Launches Worldwide - Reuters"
    ) == '"OpenAI GPT-6" Model'


@pytest.mark.unit
def test_discovery_clusters_headline_variants_and_keeps_lineage(monkeypatch):
    headlines = [
        {"external_id": "one", "title": "Nova AI model launches worldwide - Reuters",
         "body": "", "created_utc": 10.0, "publisher": "Reuters", "category": "technology",
         "region": "US", "rank": 0},
        {"external_id": "two", "title": "Nova AI model launched around world - BBC",
         "body": "", "created_utc": 11.0, "publisher": "BBC", "category": "world",
         "region": "GB", "rank": 1},
    ]
    monkeypatch.setattr(
        poller, "fetch_top_news_headlines", lambda **_kwargs: headlines
    )
    monkeypatch.setattr(poller, "fetch_x_trends", lambda _, **_kwargs: [])

    topics = poller.discover_x_topics(max_topics=1)

    assert len(topics) == 1
    assert {row["external_id"] for row in topics[0]["lineage"]} == {"one", "two"}
    assert topics[0]["regions"] == {"US", "GB"}


@pytest.mark.unit
def test_discovery_never_spends_search_budget_on_general_only_topic():
    headlines = [{
        "external_id": "general-1",
        "title": "Major public story develops - Reuters",
        "body": "",
        "created_utc": 10.0,
        "publisher": "Reuters",
        "category": "general",
        "region": "US",
        "rank": 0,
    }]

    assert poller.discover_x_topics(
        max_topics=3, headlines=headlines, trends=[]
    ) == []


@pytest.mark.unit
def test_paid_topic_search_requires_formally_independent_editorial_lineage():
    captured = 1_800_000_000.0
    base = {
        "topic": "trend_technology", "category": "technology",
        "query": '"Nova" model', "external_id": "story",
        "title": "Nova model launches", "body": "report",
        "created_utc": captured - 10,
    }
    sponsored_capable = {
        **base,
        "publisher": "TechCrunch",
        "metadata": {"publisher_domain": "techcrunch.com"},
    }
    independent = {
        **base,
        "external_id": "independent",
        "publisher": "Reuters",
        "metadata": {"publisher_domain": "reuters.com"},
    }

    assert poller._formally_grounded_discovery_topics(
        [sponsored_capable], captured
    ) == []
    assert poller._formally_grounded_discovery_topics(
        [independent], captured
    ) == [independent]

    stale = {**independent, "created_utc": captured - 7 * 86400 - 1}
    future = {**independent, "created_utc": captured + 1}
    missing_identity = {**independent, "external_id": ""}
    corporate = {
        **independent,
        "metadata": {
            **independent["metadata"],
            "verified_type": "business",
        },
    }
    assert poller._formally_grounded_discovery_topics(
        [stale, future, missing_identity, corporate], captured
    ) == []


@pytest.mark.unit
def test_paid_topic_search_requires_a_finite_capture_time():
    with pytest.raises(ValueError, match="capture time must be finite"):
        poller._formally_grounded_discovery_topics([], float("nan"))


@pytest.mark.unit
def test_x_discovery_cycle_has_independent_daily_clock(tmp_path, monkeypatch):
    now = _X_WINDOW_OPEN_UTC
    store = SqliteMediaStore(tmp_path / "media.db")
    topic = {
        "topic": "trend_world", "category": "world", "query": '"Bordeaux" wildfires',
        "external_id": "headline-1", "title": "Wildfires force Bordeaux evacuations - Reuters",
        "body": "summary", "created_utc": now - 10, "publisher": "Reuters",
        "metadata": {
            "article_url": "https://news.google.com/articles/headline-1",
            "publisher_domain": "reuters.com",
        },
    }
    trend_limits = []

    def fetch_trends(_woeid, *, limit):
        trend_limits.append(limit)
        return [{"name": "Global event"}]

    monkeypatch.setattr(poller.time, "time", lambda: now)
    monkeypatch.setattr(poller, "fetch_x_trends", fetch_trends)
    monkeypatch.setattr(
        poller, "discover_x_topics", lambda max_topics, **kwargs: [topic]
    )
    monkeypatch.setattr(
        poller, "fetch_top_news_headlines", lambda **_kwargs: [topic]
    )
    monkeypatch.setattr(
        poller, "fetch_x_topic",
        lambda topic, query, now, limit: [
            _row("x", "post-1", f"@{topic}", now, created_utc=now, body=query)
        ],
    )

    poller.poll_x_topics_once(store, now=now, limit=10, max_topics=3)

    assert store.get_meta("last_x_poll_utc") == now
    stats = {(row[0], row[1]) for row in store.stats()}
    assert ("@TREND_WORLD", "x") in stats
    assert ("@TREND_WORLD", "trendnews") in stats
    trend_receipts = store.fetch_runs(provider="xtrend")
    search_receipts = store.fetch_runs(provider="x")
    assert len(trend_receipts) == 2
    assert len(search_receipts) == 1
    assert trend_limits == [
        media_sources.GLOBAL_X_ADAPTER_POLICY["trends"]["result_limit"][
            "default"
        ]
    ] * len(trend_receipts)
    x_items = store.fetch_items(search_receipts[0]["fetch_run_id"])
    assert len(x_items) == 1
    assert x_items[0]["source"] == "x"
    assert x_items[0]["external_id"] == "post-1"
    assert x_items[0]["observed_utc"] == search_receipts[0]["received_utc"]
    assert x_items[0]["raw_content_id"].startswith("raw_")
    assert search_receipts[0]["formal_eligible_lineage"] == []
    for receipt in trend_receipts + search_receipts:
        assert receipt["cost_units"] == 1.0
        assert "budget_reservation" in receipt["metadata_json"]
    cycle_ids = {
        receipt["collection_cycle_id"]
        for receipt in trend_receipts + search_receipts
    }
    assert len(cycle_ids) == 1
    cycle = store.collection_cycle(cycle_ids.pop())
    assert cycle["status"] == "complete"
    assert poller._x_daily_requirement_state(store, now, 3) == "complete"
    next_midnight = datetime(2026, 8, 6, tzinfo=timezone.utc).timestamp()
    assert poller._x_daily_requirement_state(store, next_midnight, 3) == "scheduled"
    assert cycle["manifest_valid"] is True
    assert {
        row["status"] for row in cycle["manifest"]["slot_receipts"]
    } == {"success"}
    manifest_receipts = {
        (row["provider"], row["query_key"]): row
        for row in cycle["manifest"]["slot_receipts"]
    }
    for receipt in trend_receipts:
        items = store.fetch_items(receipt["fetch_run_id"])
        assert items
        assert manifest_receipts[(receipt["provider"], receipt["query_key"])][
            "raw_content_ids"
        ] == sorted(item["raw_content_id"] for item in items)
    tampered_item = store.fetch_items(trend_receipts[0]["fetch_run_id"])[0]
    store.conn.execute(
        "UPDATE media_posts SET body='tampered trend response' "
        "WHERE source=? AND external_id=?",
        (tampered_item["source"], tampered_item["external_id"]),
    )
    store.conn.commit()
    with pytest.raises(ValueError, match="raw-content replay detected tampering"):
        store.collection_cycle(cycle["collection_cycle_id"])
    store.close()


@pytest.mark.unit
def test_observed_empty_x_search_is_valid_cycle_coverage(tmp_path, monkeypatch):
    now = _X_WINDOW_OPEN_UTC
    store = SqliteMediaStore(tmp_path / "media.db")
    topic = {
        "topic": "trend_world", "category": "world", "query": '"Global event" reaction',
        "external_id": "headline-1", "title": "Global event develops - Reuters",
        "body": "summary", "created_utc": now - 10, "publisher": "Reuters",
        "metadata": {
            "article_url": "https://news.google.com/articles/headline-1",
            "publisher_domain": "reuters.com",
        },
    }
    alerts = []
    monkeypatch.setattr(poller.time, "time", lambda: now)
    monkeypatch.setattr(
        poller,
        "fetch_x_trends",
        lambda woeid, **_kwargs: [{"name": "Global event"}],
    )
    monkeypatch.setattr(
        poller, "discover_x_topics", lambda max_topics, **kwargs: [topic]
    )
    monkeypatch.setattr(
        poller, "fetch_top_news_headlines", lambda **_kwargs: [topic]
    )
    monkeypatch.setattr(poller, "fetch_x_topic", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda component, event, **kwargs: alerts.append((component, event, kwargs)),
    )

    poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )

    assert alerts == []
    assert store.get_meta("poller:last_success_utc") == now
    assert store.get_meta("poller:last_failure_utc") is None
    cycle_id = poller._x_collection_cycle_spec(now, 3)["collection_cycle_id"]
    cycle = store.collection_cycle(cycle_id)
    assert cycle["status"] == "complete"
    outcomes = {
        (row["provider"], row["query_key"]): row["status"]
        for row in cycle["manifest"]["slot_receipts"]
    }
    assert outcomes[("x", topic["query"])] == "empty"
    store.close()


@pytest.mark.unit
def test_x_source_enables_discovery_not_per_ticker_queries(tmp_path, monkeypatch):
    captured = {}

    def fake_run_cycle(store, tickers, sources, macro_themes, x_enabled,
                       x_interval, x_limit, x_topic_limit, force_x):
        captured.update(
            tickers=tickers,
            sources=sources,
            x_enabled=x_enabled,
            x_interval=x_interval,
            x_limit=x_limit,
            x_topic_limit=x_topic_limit,
            force_x=force_x,
        )

    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(poller, "run_cycle", fake_run_cycle)

    poller.main([
        "--tickers", "AAPL,NVDA",
        "--sources", "x",
        "--once",
        "--no-macro",
        "--db", str(tmp_path / "media.db"),
    ])

    assert captured["tickers"] == ["AAPL", "NVDA"]
    assert captured["sources"] == []
    assert captured["x_enabled"] is True
    assert captured["x_interval"] == 86400
    assert captured["x_topic_limit"] == 3
    assert captured["x_limit"] == 10
    assert captured["force_x"] is True


@pytest.mark.unit
def test_global_only_mode_runs_news_and_bounded_x_without_ticker_sources(
    tmp_path, monkeypatch,
):
    captured = {}

    def fake_run_cycle(store, tickers, sources, macro_themes, x_enabled,
                       x_interval, x_limit, x_topic_limit, force_x):
        captured.update(
            tickers=tickers,
            sources=sources,
            macro_themes=macro_themes,
            x_enabled=x_enabled,
            x_interval=x_interval,
            x_limit=x_limit,
            x_topic_limit=x_topic_limit,
            force_x=force_x,
        )

    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(poller, "run_cycle", fake_run_cycle)

    poller.main([
        "--global-only",
        "--sources", "x",
        "--once",
        "--no-trading-hours",
        "--interval", "3600",
        "--x-interval", "86400",
        "--db", str(tmp_path / "global.db"),
    ])

    assert captured["tickers"] == []
    assert captured["sources"] == []
    assert captured["x_enabled"] is True
    assert captured["x_interval"] == 86400
    assert captured["x_topic_limit"] == 3
    assert captured["x_limit"] == 10
    assert captured["force_x"] is True
    assert len(poller._globalnews_query_slots(captured["macro_themes"])) == 10
    assert all(
        spec["prediction_topics"] == []
        for spec in captured["macro_themes"].values()
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "extra_args",
    [
        ["--tickers", "AAPL"],
        ["--sources", "x,reddit"],
        ["--no-macro"],
    ],
)
def test_global_only_mode_rejects_tickers_ticker_sources_and_missing_news(
    tmp_path, monkeypatch, extra_args,
):
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    base = [
        "--global-only",
        "--sources", "x",
        "--once",
        "--no-trading-hours",
        "--interval", "3600",
        "--x-interval", "86400",
        "--db", str(tmp_path / "must-not-open.db"),
    ]
    if "--sources" in extra_args:
        base[base.index("--sources") + 1] = extra_args[1]
        extra_args = []

    with pytest.raises(SystemExit):
        poller.main([*base, *extra_args])


@pytest.mark.unit
def test_global_only_mode_requires_explicit_versioned_cadence(tmp_path, monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.delenv("MEDIA_POLLER_INTERVAL", raising=False)
    monkeypatch.delenv("MEDIA_POLLER_X_INTERVAL", raising=False)

    with pytest.raises(SystemExit):
        poller.main([
            "--global-only",
            "--sources", "x",
            "--once",
            "--no-trading-hours",
            "--db", str(tmp_path / "missing-cadence.db"),
        ])


@pytest.mark.unit
def test_global_only_daemon_fails_closed_while_collection_is_paused(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setenv("MEDIA_COLLECTION_ENABLED", "false")
    monkeypatch.setattr(
        poller,
        "open_store",
        lambda *_args, **_kwargs: pytest.fail("paused daemon opened the database"),
    )

    with pytest.raises(SystemExit):
        poller.main([
            "--global-only",
            "--sources", "x",
            "--no-trading-hours",
            "--interval", "3600",
            "--x-interval", "86400",
            "--db", str(tmp_path / "paused.db"),
        ])


@pytest.mark.unit
def test_explicit_x_source_fails_startup_without_nonblank_credentials(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("X_BEARER_TOKEN", "   ")

    with pytest.raises(SystemExit):
        poller.main([
            "--sources", "x", "--once", "--no-macro",
            "--db", str(tmp_path / "missing-token.db"),
        ])


@pytest.mark.unit
def test_x_cycle_manifest_distinguishes_failed_trend_and_empty_search(
    tmp_path, monkeypatch,
):
    now = _X_WINDOW_OPEN_UTC
    store = SqliteMediaStore(tmp_path / "x-failure.db")
    topic = {
        "topic": "trend_world",
        "category": "world",
        "query": '"Global event" reaction',
        "external_id": "headline-1",
        "title": "Global event develops - Reuters",
        "body": "summary",
        "created_utc": now - 10,
        "publisher": "Reuters",
        "metadata": {
            "article_url": "https://news.google.com/articles/headline-1",
            "publisher_domain": "reuters.com",
        },
    }
    monkeypatch.setattr(poller.time, "time", lambda: now)
    monkeypatch.setattr(
        poller, "fetch_top_news_headlines", lambda **_kwargs: [topic]
    )
    monkeypatch.setattr(
        poller,
        "fetch_x_trends",
        lambda woeid, **_kwargs: (_ for _ in ()).throw(
            poller.ProviderTransientError("unavailable")
        )
        if woeid == 1 else [{"name": "Global event"}],
    )
    monkeypatch.setattr(
        poller, "discover_x_topics", lambda max_topics, **kwargs: [topic]
    )
    monkeypatch.setattr(poller, "fetch_x_topic", lambda *args, **kwargs: [])

    poller.poll_x_topics_once(store, now=now, limit=10, max_topics=3)

    cycle_id = poller._x_collection_cycle_spec(now, 3)["collection_cycle_id"]
    cycle = store.collection_cycle(cycle_id)
    outcomes = {
        (row["provider"], row["query_key"]): row["status"]
        for row in cycle["manifest"]["slot_receipts"]
    }
    assert cycle["status"] == "incomplete"
    assert outcomes[("xtrend", "woeid:1")] == "failed"
    assert outcomes[("xtrend", "woeid:23424977")] == "missing"
    assert outcomes[("trendnews", "ranked-global-discovery")] == "missing"
    assert all(provider != "x" for provider, _ in outcomes)
    assert poller._x_daily_requirement_state(store, now, 3) == "incomplete"

    alerts = []
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda component, event, **kwargs: alerts.append(
            (component, event, kwargs)
        ) or True,
    )
    coverage = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
    )
    assert coverage["complete"] is False
    assert coverage["missing_query_slots"] == []
    assert coverage["periodic_requirements"] == {"x_daily": "incomplete"}
    assert coverage["missing_periodic_requirements"] == ["x_daily"]
    assert alerts[0][1] == "query_slot_coverage_incomplete"
    assert alerts[0][2]["details"]["missing_x_daily_requirement"] is True
    store.close()


@pytest.mark.unit
def test_discovery_feed_failure_never_starts_or_spends_paid_x_cycle(
    tmp_path, monkeypatch,
):
    now = _X_WINDOW_OPEN_UTC
    store = SqliteMediaStore(tmp_path / "x-news-partial.db")
    monkeypatch.setattr(poller.time, "time", lambda: now)
    monkeypatch.setattr(
        poller,
        "fetch_x_trends",
        lambda _, **_kwargs: pytest.fail(
            "free discovery must be validated before paid X"
        ),
    )
    monkeypatch.setattr(
        poller,
        "fetch_top_news_headlines",
        lambda **_kwargs: (_ for _ in ()).throw(
            poller.ProviderTransientError("top-news discovery feed set was incomplete")
        ),
    )

    slots = poller.poll_x_topics_once(store, now=now, limit=10, max_topics=3)

    cycle_id = poller._x_collection_cycle_spec(now, 3)["collection_cycle_id"]
    assert store.collection_cycle(cycle_id) is None
    assert store.fetch_runs(limit=100) == []
    day_start = datetime(2026, 8, 5, tzinfo=timezone.utc).timestamp()
    assert store.daily_cost_units("xtrend", day_start, day_start + 86400) == 0.0
    assert set(slots) == {
        ("xtrend", "woeid:1"),
        ("xtrend", "woeid:23424977"),
        ("trendnews", "ranked-global-discovery"),
    }
    assert all(provider != "x" for provider, _ in slots)

    alerts = []
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda component, event, **kwargs: alerts.append(
            (component, event, kwargs)
        ) or True,
    )
    coverage = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )
    assert coverage["complete"] is False
    assert coverage["periodic_requirements"] == {"x_daily": "missing"}
    assert coverage["missing_periodic_requirements"] == ["x_daily"]
    assert alerts[0][2]["details"] == {
        "expected_query_slot_count": 0,
        "missing_query_slot_count": 0,
        "missing_periodic_requirement_count": 1,
        "missing_x_daily_requirement": True,
        "x_daily_state": "missing",
        "missing_source_group_count": 0,
        "reason_counts": {},
        "slots": [],
        "slots_truncated": 0,
    }
    poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )
    assert len(alerts) == 1
    store.close()


@pytest.mark.unit
def test_same_daily_x_cycle_cannot_retry_paid_requests(tmp_path, monkeypatch):
    now = _X_WINDOW_OPEN_UTC
    store = SqliteMediaStore(tmp_path / "x-no-retry.db")
    topic = {
        "topic": "trend_technology",
        "category": "technology",
        "query": '"Nova model" launch',
        "external_id": "headline-1",
        "title": "Nova model launches - Reuters",
        "body": "summary",
        "created_utc": now - 10,
        "publisher": "Reuters",
        "metadata": {
            "article_url": "https://news.google.com/articles/headline-1",
            "publisher_domain": "reuters.com",
        },
    }
    monkeypatch.setattr(poller.time, "time", lambda: now)
    monkeypatch.setattr(
        poller, "fetch_top_news_headlines", lambda **_kwargs: [topic]
    )
    monkeypatch.setattr(poller, "fetch_x_trends", lambda _, **_kwargs: [])
    monkeypatch.setattr(
        poller, "discover_x_topics", lambda max_topics, **kwargs: [topic]
    )
    monkeypatch.setattr(poller, "fetch_x_topic", lambda *args, **kwargs: [])

    poller.poll_x_topics_once(store, now=now, limit=10, max_topics=3)
    first_receipts = store.fetch_runs(limit=100)
    monkeypatch.setattr(
        poller, "fetch_x_trends",
        lambda _, **_kwargs: pytest.fail(
            "terminal cycle reuse must not fetch trends"
        ),
    )
    monkeypatch.setattr(
        poller, "fetch_top_news_headlines",
        lambda **_kwargs: pytest.fail("terminal cycle reuse must not fetch news"),
    )
    monkeypatch.setattr(
        poller, "fetch_x_topic",
        lambda *args, **kwargs: pytest.fail("terminal cycle reuse must not search"),
    )
    reused_slots = poller.poll_x_topics_once(
        store, now=now, limit=10, max_topics=3
    )

    assert len(store.fetch_runs(limit=100)) == len(first_receipts)
    assert ("x", topic["query"]) in reused_slots
    day_start = datetime(2026, 8, 5, tzinfo=timezone.utc).timestamp()
    assert store.daily_cost_units("xtrend", day_start, day_start + 86400) == 2.0
    assert store.daily_cost_units("x", day_start, day_start + 86400) == 1.0
    store.close()


@pytest.mark.unit
def test_duplicate_derived_queries_form_one_bound_request_with_all_labels(
    tmp_path, monkeypatch,
):
    now = _X_WINDOW_OPEN_UTC
    store = SqliteMediaStore(tmp_path / "x-grouped-query.db")
    topics = [
        {
            "topic": "trend_world",
            "category": "world",
            "query": '"Shared event" reaction',
            "external_id": "world-story",
            "title": "Shared event changes world outlook - Reuters",
            "created_utc": now - 10,
            "publisher": "Reuters",
            "metadata": {"publisher_domain": "reuters.com"},
        },
        {
            "topic": "trend_business",
            "category": "business",
            "query": '"Shared event" reaction',
            "external_id": "business-story",
            "title": "Shared event changes markets - Reuters",
            "created_utc": now - 9,
            "publisher": "Reuters",
            "metadata": {"publisher_domain": "reuters.com"},
        },
    ]
    calls = []
    monkeypatch.setattr(poller.time, "time", lambda: now)
    monkeypatch.setattr(
        poller, "fetch_top_news_headlines", lambda **_kwargs: topics
    )
    monkeypatch.setattr(poller, "fetch_x_trends", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        poller, "discover_x_topics", lambda max_topics, **_kwargs: topics
    )
    monkeypatch.setattr(
        poller,
        "fetch_x_topic",
        lambda topic, query, now, limit: calls.append(
            (topic, query, now, limit)
        ) or [],
    )

    poller.poll_x_topics_once(store, now=now, limit=10, max_topics=3)

    cycle_id = poller._x_collection_cycle_spec(now, 3)["collection_cycle_id"]
    cycle = store.collection_cycle(cycle_id)
    assert calls == [("trend_business", '"Shared event" reaction', now, 10)]
    assert cycle["status"] == "complete"
    assert cycle["manifest"]["expected_dynamic_slots"] == [{
        "provider": "x",
        "query_key": '"Shared event" reaction',
    }]
    receipt = store.fetch_runs(provider="x")[0]
    assert json.loads(receipt["metadata_json"])["labels"] == [
        "@TREND_BUSINESS",
        "@TREND_WORLD",
    ]
    decision_items = store.collection_cycle_item_rows(
        cycle_id,
        provider="trendnews",
        query_key="ranked-global-discovery",
    )
    decisions = [
        json.loads(item["row"]["body"])
        for item in decision_items
        if item["row"].get("ticker") == "@X_DISCOVERY_AUDIT"
    ]
    assert len(decisions) == 1
    poller.validate_x_discovery_decision(decisions[0])
    assert decisions[0]["search_requests"][0]["labels"] == [
        "@TREND_BUSINESS",
        "@TREND_WORLD",
    ]
    store.close()


@pytest.mark.unit
def test_restart_recovers_running_daily_cycle_without_an_external_retry(
    tmp_path, monkeypatch,
):
    store = SqliteMediaStore(tmp_path / "x-recovery.db")
    clock = {"now": 101.0}
    monkeypatch.setattr(poller.time, "time", lambda: clock["now"])
    spec = poller._x_collection_cycle_spec(100.0, 3)
    cycle_id = store.start_collection_cycle(spec, started_utc=-1000.0)
    orphan = store.start_budgeted_fetch(
        "xtrend",
        "woeid:1",
        -999.0,
        collection_cycle_id=cycle_id,
        budget_limits={"x-budget:trend:1970-01-01:total": 2.0},
        metadata={"kind": "media", "budget_category": "trend"},
    )
    monkeypatch.setattr(
        poller,
        "fetch_x_trends",
        lambda _, **_kwargs: pytest.fail(
            "recovery must not retry a paid trend request"
        ),
    )
    monkeypatch.setattr(
        poller,
        "fetch_top_news_headlines",
        lambda **_kwargs: pytest.fail("recovery must not rerun discovery"),
    )
    monkeypatch.setattr(
        poller,
        "fetch_x_topic",
        lambda *args, **kwargs: pytest.fail("recovery must not retry paid search"),
    )
    clock["now"] += float(
        poller.GLOBAL_EVENT_V2_PROTOCOL["evidence"][
            "x_cycle_recovery_stale_seconds"
        ]
    ) + 1.0

    slots = poller.poll_x_topics_once(store, now=100.0, limit=10, max_topics=3)

    cycle = store.collection_cycle(cycle_id)
    orphan_receipt = next(
        row for row in store.fetch_runs(limit=100) if row["fetch_run_id"] == orphan
    )
    outcomes = {
        (row["provider"], row["query_key"]): row["status"]
        for row in cycle["manifest"]["slot_receipts"]
    }
    assert cycle["status"] == "incomplete"
    assert orphan_receipt["status"] == "failed"
    assert orphan_receipt["error"] == "collector_restart_recovery"
    assert outcomes[("xtrend", "woeid:1")] == "failed"
    assert outcomes[("xtrend", "woeid:23424977")] == "missing"
    assert outcomes[("trendnews", "ranked-global-discovery")] == "missing"
    assert set(slots) == {
        ("xtrend", "woeid:1"),
        ("xtrend", "woeid:23424977"),
        ("trendnews", "ranked-global-discovery"),
    }
    assert store.get_meta("last_x_poll_utc") == 100.0
    assert store.get_meta("x-budget:trend:1970-01-01:total") == 1.0
    store.close()


@pytest.mark.unit
def test_concurrent_contender_noops_while_daily_cycle_owner_is_fresh(
    tmp_path, monkeypatch,
):
    store = SqliteMediaStore(tmp_path / "x-fresh-owner.db")
    monkeypatch.setattr(poller.time, "time", lambda: 101.0)
    spec = poller._x_collection_cycle_spec(100.0, 3)
    cycle_id = store.start_collection_cycle(spec, started_utc=100.0)
    owner_receipt = store.start_budgeted_fetch(
        "xtrend",
        "woeid:1",
        100.5,
        collection_cycle_id=cycle_id,
        budget_limits={"x-budget:fresh-owner": 1.0},
        metadata={"kind": "media", "budget_category": "trend"},
    )
    monkeypatch.setattr(
        poller,
        "fetch_x_trends",
        lambda _, **_kwargs: pytest.fail(
            "a contender must not issue an external request"
        ),
    )

    slots = poller.poll_x_topics_once(store, now=100.0, limit=10, max_topics=3)

    cycle = store.collection_cycle(cycle_id)
    receipt = next(
        row for row in store.fetch_runs(limit=100)
        if row["fetch_run_id"] == owner_receipt
    )
    assert cycle["status"] == "running"
    assert receipt["status"] == "running"
    assert store.get_meta("x-budget:fresh-owner") == 1.0
    assert store.get_meta("last_x_poll_utc") is None
    assert set(slots) == {
        ("xtrend", "woeid:1"),
        ("xtrend", "woeid:23424977"),
        ("trendnews", "ranked-global-discovery"),
    }
    store.close()


@pytest.mark.unit
def test_receiptless_x_period_is_incomplete_and_utc_date_keyed(tmp_path, monkeypatch):
    now = _X_WINDOW_OPEN_UTC
    store = SqliteMediaStore(tmp_path / "x-period.db")
    monkeypatch.setattr(poller.time, "time", lambda: now)
    spec = poller._x_collection_cycle_spec(now, 3)
    cycle_id = store.start_collection_cycle(spec, started_utc=now)
    store.finish_collection_cycle(cycle_id, completed_utc=now + 1)

    assert poller._x_daily_requirement_state(store, now, 3) == "incomplete"
    next_midnight = datetime(2026, 8, 6, tzinfo=timezone.utc).timestamp()
    assert poller._x_daily_requirement_state(store, next_midnight, 3) == "scheduled"
    next_closed = datetime(2026, 8, 6, 23, 46, tzinfo=timezone.utc).timestamp()
    assert poller._x_daily_requirement_state(store, next_closed, 3) == "missing"
    with pytest.raises(ValueError, match="frozen protocol"):
        poller.run_cycle(
            store,
            tickers=[],
            sources=[],
            macro_themes={},
            x_enabled=True,
            x_interval=86399,
        )
    store.close()


@pytest.mark.unit
def test_x_cycle_is_scheduled_before_window_even_when_forced(tmp_path, monkeypatch):
    now = datetime(2026, 8, 5, 20, 59, tzinfo=timezone.utc).timestamp()
    store = SqliteMediaStore(tmp_path / "x-before-window.db")
    monkeypatch.setattr(poller.time, "time", lambda: now)
    monkeypatch.setattr(
        poller,
        "fetch_top_news_headlines",
        lambda **_kwargs: pytest.fail("scheduled X must not fetch discovery input"),
    )
    monkeypatch.setattr(
        poller,
        "fetch_x_trends",
        lambda *_args, **_kwargs: pytest.fail("scheduled X must not fetch trends"),
    )
    monkeypatch.setattr(
        poller,
        "fetch_x_topic",
        lambda *_args, **_kwargs: pytest.fail("scheduled X must not search"),
    )
    alerts = []
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda *args, **kwargs: alerts.append((args, kwargs)) or True,
    )

    coverage = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )

    assert coverage["periodic_requirements"] == {"x_daily": "scheduled"}
    assert coverage["missing_periodic_requirements"] == []
    assert coverage["complete"] is True
    assert coverage["query_slots"] == []
    assert store.fetch_runs() == []
    assert alerts == []
    store.close()


@pytest.mark.unit
def test_x_cycle_does_not_start_near_utc_midnight_and_reports_missing(
    tmp_path, monkeypatch,
):
    now = _X_WINDOW_CLOSED_UTC
    store = SqliteMediaStore(tmp_path / "x-midnight-boundary.db")
    monkeypatch.setattr(poller.time, "time", lambda: now)
    monkeypatch.setattr(
        poller,
        "fetch_top_news_headlines",
        lambda **_kwargs: pytest.fail("late cycle must not fetch discovery input"),
    )
    alerts = []
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda *args, **kwargs: alerts.append((args, kwargs)) or True,
    )

    coverage = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )

    assert store.fetch_runs() == []
    assert store.collection_cycle(
        poller._x_collection_cycle_spec(now, 3)["collection_cycle_id"]
    ) is None
    assert coverage["periodic_requirements"] == {"x_daily": "missing"}
    assert coverage["missing_periodic_requirements"] == ["x_daily"]
    assert coverage["complete"] is False
    assert len(alerts) == 1
    store.close()


@pytest.mark.unit
def test_scheduled_period_preserves_prior_x_incident_until_x_completes(
    tmp_path, monkeypatch,
):
    first_open = _X_WINDOW_OPEN_UTC
    next_scheduled = datetime(2026, 8, 6, 0, 5, tzinfo=timezone.utc).timestamp()
    next_open = datetime(2026, 8, 6, 21, tzinfo=timezone.utc).timestamp()
    clock = {"now": first_open}
    store = SqliteMediaStore(tmp_path / "x-incident-boundary.db")
    monkeypatch.setattr(poller.time, "time", lambda: clock["now"])
    calls = []

    def unavailable_news(**_kwargs):
        calls.append(clock["now"])
        raise poller.ProviderTransientError("temporarily unavailable")

    alerts = []
    monkeypatch.setattr(poller, "fetch_top_news_headlines", unavailable_news)
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda _component, event, **_kwargs: alerts.append(event) or True,
    )

    failed = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
    )
    clock["now"] = next_scheduled
    scheduled = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )

    assert failed["periodic_requirements"] == {"x_daily": "missing"}
    assert scheduled["periodic_requirements"] == {"x_daily": "scheduled"}
    assert scheduled["complete"] is True
    assert calls == [first_open]
    assert alerts == ["query_slot_coverage_incomplete"]
    assert store.get_meta(poller._COVERAGE_ALERT_STATE_KEY) == 1.0

    topic = {
        "topic": "trend_world",
        "category": "world",
        "query": '"Global event" reaction',
        "external_id": "headline-2",
        "title": "Global event develops - Reuters",
        "body": "summary",
        "created_utc": next_open - 10,
        "publisher": "Reuters",
        "metadata": {"publisher_domain": "reuters.com"},
    }
    monkeypatch.setattr(
        poller, "fetch_top_news_headlines", lambda **_kwargs: [topic]
    )
    monkeypatch.setattr(
        poller, "fetch_x_trends", lambda *_args, **_kwargs: [{"name": "Global event"}]
    )
    monkeypatch.setattr(
        poller, "discover_x_topics", lambda *_args, **_kwargs: [topic]
    )
    monkeypatch.setattr(poller, "fetch_x_topic", lambda *_args, **_kwargs: [])
    clock["now"] = next_open

    recovered = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
    )

    assert recovered["periodic_requirements"] == {"x_daily": "complete"}
    assert recovered["complete"] is True
    assert alerts == [
        "query_slot_coverage_incomplete",
        "query_slot_coverage_recovered",
    ]
    assert store.get_meta(poller._COVERAGE_ALERT_STATE_KEY) == 0.0
    store.close()


@pytest.mark.unit
def test_failed_open_window_attempt_stays_missing_after_start_window_closes(
    tmp_path, monkeypatch,
):
    open_now = _X_WINDOW_OPEN_UTC
    closed_now = _X_WINDOW_CLOSED_UTC
    clock = {"now": open_now}
    alerts = []
    store = SqliteMediaStore(tmp_path / "x-failed-before-midnight.db")
    monkeypatch.setattr(poller.time, "time", lambda: clock["now"])
    monkeypatch.setattr(
        poller,
        "fetch_top_news_headlines",
        lambda **_kwargs: (_ for _ in ()).throw(
            poller.ProviderTransientError("temporarily unavailable")
        ),
    )
    monkeypatch.setattr(
        poller,
        "emit_alert",
        lambda *args, **kwargs: alerts.append((args, kwargs)) or True,
    )

    first = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )
    clock["now"] = closed_now
    second = poller.run_cycle(
        store,
        tickers=[],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )

    assert first["periodic_requirements"] == {"x_daily": "missing"}
    assert second["periodic_requirements"] == {"x_daily": "missing"}
    assert second["missing_periodic_requirements"] == ["x_daily"]
    assert second["complete"] is False
    assert len(alerts) == 1
    store.close()


@pytest.mark.unit
def test_discovery_queries_are_derived_only_from_ranked_headlines():
    def discover(entity, external_id):
        return poller.discover_x_topics(
            max_topics=1,
            headlines=[{
                "external_id": external_id,
                "title": f"{entity} launches a new platform - Reuters",
                "body": "",
                "created_utc": 10.0,
                "publisher": "Reuters",
                "category": "technology",
                "region": "US",
                "rank": 0,
            }],
            trends=[{"name": "Unrelated entertainment trend"}],
        )[0]

    first = discover("ZephyrQuill", "first")
    second = discover("QuasarLoom", "second")

    assert first["external_id"] == "first"
    assert second["external_id"] == "second"
    assert first["query"] != second["query"]
    assert "zephyrquill" in first["query"].lower()
    assert "quasarloom" in second["query"].lower()
    assert "xtrend" not in poller.GLOBAL_EVENT_V2_PROTOCOL["evidence"]["allowed_sources"]
