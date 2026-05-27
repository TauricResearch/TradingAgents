import json
import pytest
import fakeredis.aioredis
from unittest.mock import patch, MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
async def test_polygon_news_emits_envelope(conn, tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from tradingagents.sensing.adapters.polygon_news import PolygonNewsAdapter
    monkeypatch.setenv("POLYGON_API_KEY", "fake")
    # Use "now" so the item is clearly newer than the resume cursor (which is
    # now-1h on a fresh DB).
    published = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "results": [{
            "id": "pn-1",
            "title": "Apple beats consensus",
            "description": "Q3 earnings strong",
            "tickers": ["AAPL"],
            "published_utc": published,
        }],
        "next_url": None,
    }
    m = MagicMock(); m.json.return_value = payload; m.raise_for_status = lambda: None
    with patch("tradingagents.sensing.adapters.polygon_news.requests.get",
               return_value=m):
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        a = PolygonNewsAdapter(staging_root=str(tmp_path / "staging"),
                                stream="ingest:raw")
        n = await a.poll_once(redis=r, conn=conn)
        assert n == 1

    entries = await r.xrange("ingest:raw")
    _, fields = entries[0]
    env = json.loads(fields["data"])
    assert env["source"] == "polygon_news"
    assert env["external_id"] == "pn:pn-1"
    assert "Apple beats" in env["text"]
    assert env["source_tags"]["tickers"] == ["AAPL"]
    cur = conn.execute("SELECT cursor FROM ingest_cursor "
                       "WHERE source='polygon_news'").fetchone()
    assert cur["cursor"] == published


@pytest.mark.unit
async def test_polygon_news_skips_when_cursor_unchanged(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters.polygon_news import PolygonNewsAdapter
    from tradingagents.sensing.cursor import CursorStore
    CursorStore(conn).set("polygon_news", "2026-05-26T15:00:00Z")
    monkeypatch.setenv("POLYGON_API_KEY", "fake")
    payload = {"results": [{
        "id": "pn-1", "title": "old", "description": "older",
        "tickers": [], "published_utc": "2026-05-26T14:00:00Z",
    }], "next_url": None}
    m = MagicMock(); m.json.return_value = payload; m.raise_for_status = lambda: None
    with patch("tradingagents.sensing.adapters.polygon_news.requests.get",
               return_value=m):
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        a = PolygonNewsAdapter(staging_root=str(tmp_path / "staging"),
                                stream="ingest:raw")
        n = await a.poll_once(redis=r, conn=conn)
    assert n == 0
