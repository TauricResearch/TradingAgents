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
                "author_id": "author-1",
                "created_at": "2026-07-22T12:00:00Z",
                "text": "People react to a major story",
            }]
        }

    monkeypatch.setenv("X_BEARER_TOKEN", "secret-test-token")
    monkeypatch.setattr(media_sources, "_get_json", fake_get_json)

    rows = media_sources.fetch_x_topic(
        "trend_world", '"Bordeaux" wildfires', 123.0, limit=3
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
def test_x_discovery_cycle_has_independent_daily_clock(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "media.db")
    topic = {
        "topic": "trend_world", "category": "world", "query": '"Bordeaux" wildfires',
        "external_id": "headline-1", "title": "Wildfires force Bordeaux evacuations - Reuters",
        "body": "summary", "created_utc": 90.0, "publisher": "Reuters",
    }
    monkeypatch.setattr(poller, "discover_x_topics", lambda max_topics: [topic])
    monkeypatch.setattr(
        poller, "fetch_x_topic",
        lambda topic, query, now, limit: [
            _row("x", "post-1", f"@{topic}", now, created_utc=now, body=query)
        ],
    )

    poller.poll_x_topics_once(store, now=100.0, limit=10, max_topics=3)

    assert store.get_meta("last_x_poll_utc") == 100.0
    assert poller._x_poll_due(store, now=100.0 + 86399, interval=86400) is False
    assert poller._x_poll_due(store, now=100.0 + 86400, interval=86400) is True
    stats = {(row[0], row[1]) for row in store.stats()}
    assert ("@TREND_WORLD", "x") in stats
    assert ("@TREND_WORLD", "trendnews") in stats
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
def test_discovery_has_no_fixed_entity_watchlist():
    source = Path(poller.__file__).read_text(encoding="utf-8")
    assert "DEFAULT_X_TOPICS" not in source
    assert "OpenAI OR" not in source
    assert "Trump OR" not in source
