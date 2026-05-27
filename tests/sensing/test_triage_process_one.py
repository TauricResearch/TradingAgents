import json
import pytest
import fakeredis.aioredis
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence.store import upsert_ticker, get_active_watchlist
from tradingagents.sensing.envelope import Envelope


def _env(text="Apple reports a big beat on Q3 revenue", source="polygon_news",
         tags=None):
    return Envelope(
        source=source,
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        external_id=f"x:{text[:5]}",
        text=text, source_tags=tags or {}, raw_path="data/events/staging/x.json",
    )


@pytest.fixture
def conn(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    upsert_ticker(conn, ticker="AAPL", exchange="NASDAQ",
                  name="Apple Inc.", aliases=[], active=True)
    return conn


def _make_llm(salience=0.9, conf=0.95, ticker="AAPL"):
    def call(_prompt):
        return json.dumps({
            "salience": salience,
            "matched_tickers": [ticker],
            "mentioned_tickers": [{"ticker": ticker, "confidence": conf}],
            "reason": "test",
        })
    return call


@pytest.mark.unit
async def test_process_one_writes_event_and_promotes(conn, tmp_path):
    from tradingagents.sensing.triage import Triage
    from tradingagents.sensing.embeddings import MockEmbedder
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    t = Triage(conn=conn, redis=r, embedder=MockEmbedder(),
               llm_call=_make_llm(),
               data_dir=str(tmp_path / "data"))
    res = await t.process_one(_env())
    assert res.status == "triaged"
    row = conn.execute(
        "SELECT * FROM events WHERE event_id = ?", (res.event_id,)
    ).fetchone()
    assert row["salience"] == pytest.approx(0.9)
    et = conn.execute(
        "SELECT * FROM event_ticker WHERE event_id = ?", (res.event_id,)
    ).fetchone()
    assert et["ticker"] == "AAPL"
    assert "AAPL" in get_active_watchlist(conn)


@pytest.mark.unit
async def test_process_one_duplicate_does_not_promote(conn, tmp_path):
    from tradingagents.sensing.triage import Triage
    from tradingagents.sensing.embeddings import MockEmbedder
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    t = Triage(conn=conn, redis=r, embedder=MockEmbedder(),
               llm_call=_make_llm(),
               data_dir=str(tmp_path / "data"))
    env = _env(text="Same exact text", source="rss")
    res1 = await t.process_one(env)
    res2 = await t.process_one(env)  # exact replay
    assert res2.status == "duplicate"
    assert res2.deduped_of == res1.event_id
    n = conn.execute(
        "SELECT COUNT(*) FROM event_ticker WHERE event_id = ?", (res2.event_id,)
    ).fetchone()[0]
    assert n == 0


@pytest.mark.unit
async def test_process_one_drops_unknown_tickers(conn, tmp_path):
    from tradingagents.sensing.triage import Triage
    from tradingagents.sensing.embeddings import MockEmbedder
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    t = Triage(conn=conn, redis=r, embedder=MockEmbedder(),
               llm_call=_make_llm(ticker="NOTREAL"),
               data_dir=str(tmp_path / "data"))
    res = await t.process_one(_env())
    rows = conn.execute(
        "SELECT * FROM event_ticker WHERE event_id = ?", (res.event_id,)
    ).fetchall()
    assert rows == []


@pytest.mark.unit
async def test_process_one_below_threshold_no_promote(conn, tmp_path):
    from tradingagents.sensing.triage import Triage
    from tradingagents.sensing.embeddings import MockEmbedder
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    t = Triage(conn=conn, redis=r, embedder=MockEmbedder(),
               llm_call=_make_llm(salience=0.5),
               data_dir=str(tmp_path / "data"))
    res = await t.process_one(_env())
    assert res.status == "triaged"
    assert "AAPL" not in get_active_watchlist(conn)
