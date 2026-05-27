import json
import pytest
import fakeredis.aioredis
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


def _feed_with_entries(*titles):
    f = MagicMock()
    f.entries = []
    for i, t in enumerate(titles):
        e = MagicMock()
        e.id = f"rss:e:{i}"
        e.title = t
        e.summary = "body"
        e.link = f"https://x/{i}"
        e.published_parsed = (2026, 5, 26, 12, 0, i, 0, 0, 0)  # struct_time
        f.entries.append(e)
    return f


@pytest.mark.unit
async def test_rss_polls_each_feed(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters import rss as rss_mod
    parse_calls = []
    def fake_parse(url):
        parse_calls.append(url)
        return _feed_with_entries(f"entry from {url}")
    monkeypatch.setattr(rss_mod.feedparser, "parse", fake_parse)
    a = rss_mod.RssAdapter(
        feeds=["https://a/rss", "https://b/rss"],
        staging_root=str(tmp_path / "s"),
        stream="ingest:raw",
    )
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    n = await a.poll_once(redis=r, conn=conn)
    assert n == 2
    assert sorted(parse_calls) == ["https://a/rss", "https://b/rss"]


@pytest.mark.unit
async def test_rss_per_feed_cursor(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters import rss as rss_mod
    monkeypatch.setattr(rss_mod.feedparser, "parse",
                        lambda url: _feed_with_entries("only one"))
    a = rss_mod.RssAdapter(
        feeds=["https://feed-a/rss"],
        staging_root=str(tmp_path / "s"),
        stream="ingest:raw",
    )
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await a.poll_once(redis=r, conn=conn)
    row = conn.execute("SELECT cursor FROM ingest_cursor WHERE source='rss'").fetchone()
    d = json.loads(row["cursor"])
    assert "https://feed-a/rss" in d


@pytest.mark.unit
async def test_rss_skips_entries_at_or_before_cursor(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters import rss as rss_mod
    monkeypatch.setattr(rss_mod.feedparser, "parse",
                        lambda url: _feed_with_entries("e1"))
    a = rss_mod.RssAdapter(
        feeds=["https://f/rss"],
        staging_root=str(tmp_path / "s"),
        stream="ingest:raw",
    )
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    n1 = await a.poll_once(redis=r, conn=conn)
    n2 = await a.poll_once(redis=r, conn=conn)
    assert n1 == 1 and n2 == 0
