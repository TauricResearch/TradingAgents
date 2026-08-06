"""Dynamic X discovery stays broad, diverse, and tightly bounded."""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from tradingagents import poller
from tradingagents.dataflows import media_sources
from tradingagents.dataflows.media_sources import _row
from tradingagents.dataflows.media_store import SqliteMediaStore


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
                    "retweet_count": 1, "quote_count": 0,
                },
            }],
            "includes": {"users": [{
                "id": "101", "username": "publicvoice", "verified_type": "none",
                "created_at": "2020-01-01T00:00:00Z",
                "public_metrics": {
                    "followers_count": 100, "following_count": 20,
                    "tweet_count": 500,
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
    assert captured["headers"]["Authorization"] == "Bearer secret-test-token"
    assert rows[0]["ticker"] == "@TREND_WORLD"
    assert rows[0]["metadata"]["evidence_role"] == "unverified_public_reaction"
    assert rows[0]["metadata"]["author_id"] == "101"
    assert rows[0]["metadata"]["automation_signals_complete"] is True
    assert rows[0]["metadata"]["account_created_utc"] is not None
    assert 0 <= rows[0]["metadata"]["automation_risk"] <= 1


@pytest.mark.unit
def test_x_topic_excludes_official_business_accounts(monkeypatch):
    def fake_get_json(url, headers, timeout):
        return {
            "data": [
                {"id": "company-post", "author_id": "1", "text": "Announcement"},
                {"id": "person-post", "author_id": "2", "text": "My reaction"},
            ],
            "includes": {"users": [
                {"id": "1", "username": "officialco", "verified_type": "business"},
                {"id": "2", "username": "publicvoice", "verified_type": "none"},
            ]},
        }

    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(media_sources, "_get_json", fake_get_json)

    rows = media_sources.fetch_x_topic("trend_world", "major event", 123.0)

    assert [row["external_id"] for row in rows] == ["person-post"]
    assert rows[0]["author"] == "publicvoice"


@pytest.mark.unit
def test_x_missing_account_creation_is_explicitly_incomplete_and_high_risk(monkeypatch):
    def fake_get_json(url, headers, timeout):
        return {
            "data": [{
                "id": "post", "author_id": "202", "text": "A substantive public reaction",
                "created_at": "2026-07-22T12:00:00Z",
                "public_metrics": {
                    "like_count": 1, "reply_count": 0,
                    "retweet_count": 0, "quote_count": 0,
                },
            }],
            "includes": {"users": [{
                "id": "202", "username": "incomplete_user",
                "verified_type": "none",
                "public_metrics": {
                    "followers_count": 100, "following_count": 20,
                    "tweet_count": 500,
                },
            }]},
        }

    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(media_sources, "_get_json", fake_get_json)

    row = media_sources.fetch_x_topic(
        "trend_world", "major event", 1_800_000_000.0
    )[0]
    assert row["metadata"]["author_id"] == "202"
    assert row["metadata"]["account_created_utc"] is None
    assert row["metadata"]["automation_signals_complete"] is False
    assert row["metadata"]["automation_risk"] == 1.0


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
    monkeypatch.setattr(poller, "fetch_top_news_headlines", lambda: headlines)
    monkeypatch.setattr(
        poller, "fetch_x_trends",
        lambda woeid: [{"name": "Helios Labs", "tweet_count": 1000}] if woeid == 1 else [],
    )

    topics = poller.discover_x_topics(max_topics=3)

    assert [topic["category"] for topic in topics] == ["world", "business", "technology"]
    assert all(topic["query"] for topic in topics)
    assert topics[2]["query"].startswith('"Helios Labs"')
    assert {topic["external_id"] for topic in topics} == {"w1", "b1", "t1"}


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
    monkeypatch.setattr(poller, "fetch_top_news_headlines", lambda: headlines)
    monkeypatch.setattr(poller, "fetch_x_trends", lambda _: [])

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
    store = SqliteMediaStore(tmp_path / "media.db")
    topic = {
        "topic": "trend_world", "category": "world", "query": '"Bordeaux" wildfires',
        "external_id": "headline-1", "title": "Wildfires force Bordeaux evacuations - Reuters",
        "body": "summary", "created_utc": 90.0, "publisher": "Reuters",
        "metadata": {
            "article_url": "https://news.google.com/articles/headline-1",
            "publisher_domain": "reuters.com",
        },
    }
    monkeypatch.setattr(poller.time, "time", lambda: 100.0)
    monkeypatch.setattr(
        poller, "fetch_x_trends", lambda woeid: [{"name": "Global event"}]
    )
    monkeypatch.setattr(
        poller, "discover_x_topics", lambda max_topics, **kwargs: [topic]
    )
    monkeypatch.setattr(poller, "fetch_top_news_headlines", lambda: [topic])
    monkeypatch.setattr(
        poller, "fetch_x_topic",
        lambda topic, query, now, limit: [
            _row("x", "post-1", f"@{topic}", now, created_utc=now, body=query)
        ],
    )

    poller.poll_x_topics_once(store, now=100.0, limit=10, max_topics=3)

    assert store.get_meta("last_x_poll_utc") == 100.0
    assert poller._x_poll_due(store, now=86399.0, interval=86400) is False
    assert poller._x_poll_due(store, now=86400.0, interval=86400) is True
    stats = {(row[0], row[1]) for row in store.stats()}
    assert ("@TREND_WORLD", "x") in stats
    assert ("@TREND_WORLD", "trendnews") in stats
    trend_receipts = store.fetch_runs(provider="xtrend")
    search_receipts = store.fetch_runs(provider="x")
    assert len(trend_receipts) == 2
    assert len(search_receipts) == 1
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
    store = SqliteMediaStore(tmp_path / "media.db")
    topic = {
        "topic": "trend_world", "category": "world", "query": '"Global event" reaction',
        "external_id": "headline-1", "title": "Global event develops - Reuters",
        "body": "summary", "created_utc": 90.0, "publisher": "Reuters",
        "metadata": {
            "article_url": "https://news.google.com/articles/headline-1",
            "publisher_domain": "reuters.com",
        },
    }
    alerts = []
    monkeypatch.setattr(poller.time, "time", lambda: 100.0)
    monkeypatch.setattr(
        poller, "fetch_x_trends", lambda woeid: [{"name": "Global event"}]
    )
    monkeypatch.setattr(
        poller, "discover_x_topics", lambda max_topics, **kwargs: [topic]
    )
    monkeypatch.setattr(poller, "fetch_top_news_headlines", lambda: [topic])
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
    assert store.get_meta("poller:last_success_utc") == 100.0
    assert store.get_meta("poller:last_failure_utc") is None
    cycle_id = poller._x_collection_cycle_spec(100.0, 3)["collection_cycle_id"]
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
    store = SqliteMediaStore(tmp_path / "x-failure.db")
    topic = {
        "topic": "trend_world",
        "category": "world",
        "query": '"Global event" reaction',
        "external_id": "headline-1",
        "title": "Global event develops - Reuters",
        "body": "summary",
        "created_utc": 90.0,
        "publisher": "Reuters",
        "metadata": {
            "article_url": "https://news.google.com/articles/headline-1",
            "publisher_domain": "reuters.com",
        },
    }
    monkeypatch.setattr(poller.time, "time", lambda: 100.0)
    monkeypatch.setattr(poller, "fetch_top_news_headlines", lambda: [topic])
    monkeypatch.setattr(
        poller,
        "fetch_x_trends",
        lambda woeid: (_ for _ in ()).throw(RuntimeError("unavailable"))
        if woeid == 1 else [{"name": "Global event"}],
    )
    monkeypatch.setattr(
        poller, "discover_x_topics", lambda max_topics, **kwargs: [topic]
    )
    monkeypatch.setattr(poller, "fetch_x_topic", lambda *args, **kwargs: [])

    poller.poll_x_topics_once(store, now=100.0, limit=10, max_topics=3)

    cycle_id = poller._x_collection_cycle_spec(100.0, 3)["collection_cycle_id"]
    cycle = store.collection_cycle(cycle_id)
    outcomes = {
        (row["provider"], row["query_key"]): row["status"]
        for row in cycle["manifest"]["slot_receipts"]
    }
    assert cycle["status"] == "incomplete"
    assert outcomes[("xtrend", "woeid:1")] == "failed"
    assert outcomes[("xtrend", "woeid:23424977")] == "success"
    assert outcomes[("trendnews", "ranked-global-discovery")] == "success"
    assert outcomes[("x", topic["query"])] == "empty"
    store.close()


@pytest.mark.unit
def test_any_frozen_discovery_feed_failure_makes_x_cycle_incomplete(
    tmp_path, monkeypatch,
):
    store = SqliteMediaStore(tmp_path / "x-news-partial.db")
    monkeypatch.setattr(poller.time, "time", lambda: 100.0)
    monkeypatch.setattr(poller, "fetch_x_trends", lambda _: [])
    monkeypatch.setattr(
        poller,
        "fetch_top_news_headlines",
        lambda: (_ for _ in ()).throw(
            RuntimeError("top-news discovery feed set was incomplete")
        ),
    )

    slots = poller.poll_x_topics_once(store, now=100.0, limit=10, max_topics=3)

    cycle_id = poller._x_collection_cycle_spec(100.0, 3)["collection_cycle_id"]
    cycle = store.collection_cycle(cycle_id)
    outcomes = {
        (row["provider"], row["query_key"]): row["status"]
        for row in cycle["manifest"]["slot_receipts"]
    }
    assert cycle["status"] == "incomplete"
    assert outcomes[("trendnews", "ranked-global-discovery")] == "failed"
    assert outcomes[("xtrend", "woeid:1")] == "empty"
    assert outcomes[("xtrend", "woeid:23424977")] == "empty"
    assert all(provider != "x" for provider, _ in slots)
    store.close()


@pytest.mark.unit
def test_same_daily_x_cycle_cannot_retry_paid_requests(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "x-no-retry.db")
    topic = {
        "topic": "trend_technology",
        "category": "technology",
        "query": '"Nova model" launch',
        "external_id": "headline-1",
        "title": "Nova model launches - Reuters",
        "body": "summary",
        "created_utc": 90.0,
        "publisher": "Reuters",
        "metadata": {
            "article_url": "https://news.google.com/articles/headline-1",
            "publisher_domain": "reuters.com",
        },
    }
    monkeypatch.setattr(poller.time, "time", lambda: 100.0)
    monkeypatch.setattr(poller, "fetch_top_news_headlines", lambda: [topic])
    monkeypatch.setattr(poller, "fetch_x_trends", lambda _: [])
    monkeypatch.setattr(
        poller, "discover_x_topics", lambda max_topics, **kwargs: [topic]
    )
    monkeypatch.setattr(poller, "fetch_x_topic", lambda *args, **kwargs: [])

    poller.poll_x_topics_once(store, now=100.0, limit=10, max_topics=3)
    first_receipts = store.fetch_runs(limit=100)
    monkeypatch.setattr(
        poller, "fetch_x_trends",
        lambda _: pytest.fail("terminal cycle reuse must not fetch trends"),
    )
    monkeypatch.setattr(
        poller, "fetch_top_news_headlines",
        lambda: pytest.fail("terminal cycle reuse must not fetch news"),
    )
    monkeypatch.setattr(
        poller, "fetch_x_topic",
        lambda *args, **kwargs: pytest.fail("terminal cycle reuse must not search"),
    )
    reused_slots = poller.poll_x_topics_once(
        store, now=100.0, limit=10, max_topics=3
    )

    assert len(store.fetch_runs(limit=100)) == len(first_receipts)
    assert ("x", topic["query"]) in reused_slots
    assert store.daily_cost_units("xtrend", 0.0, 1000.0) == 2.0
    assert store.daily_cost_units("x", 0.0, 1000.0) == 1.0
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
        lambda _: pytest.fail("recovery must not retry a paid trend request"),
    )
    monkeypatch.setattr(
        poller,
        "fetch_top_news_headlines",
        lambda: pytest.fail("recovery must not rerun discovery"),
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
        lambda _: pytest.fail("a contender must not issue an external request"),
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
def test_x_period_due_is_utc_date_keyed_and_interval_is_frozen(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "x-period.db")
    monkeypatch.setattr(poller.time, "time", lambda: 100.0)
    spec = poller._x_collection_cycle_spec(100.0, 3)
    cycle_id = store.start_collection_cycle(spec, started_utc=100.0)
    store.finish_collection_cycle(cycle_id, completed_utc=101.0)

    assert poller._x_poll_due(store, now=86399.9, interval=86400) is False
    assert poller._x_poll_due(store, now=86400.0, interval=86400) is True
    with pytest.raises(ValueError, match="frozen protocol"):
        poller._x_poll_due(store, now=100.0, interval=86399)
    store.close()


@pytest.mark.unit
def test_discovery_has_no_fixed_entity_watchlist():
    source = Path(poller.__file__).read_text(encoding="utf-8")
    assert "DEFAULT_X_TOPICS" not in source
    assert "OpenAI OR" not in source
    assert "Trump OR" not in source
    assert "xtrend" not in poller.GLOBAL_EVENT_V2_PROTOCOL["evidence"]["allowed_sources"]
