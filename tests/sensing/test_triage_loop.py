import asyncio
import json
import pytest
import fakeredis.aioredis
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence.store import upsert_ticker
from tradingagents.sensing.envelope import Envelope
from tradingagents.sensing.redis_client import ensure_consumer_group


@pytest.fixture
def conn(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    upsert_ticker(conn, ticker="AAPL", exchange="NASDAQ",
                  name="Apple Inc.", aliases=[], active=True)
    return conn


def _llm():
    def call(_p):
        return json.dumps({"salience": 0.5, "matched_tickers": [],
                            "mentioned_tickers": [], "reason": "ok"})
    return call


@pytest.mark.unit
async def test_consume_processes_one_envelope_then_acks(conn, tmp_path):
    from tradingagents.sensing.triage import Triage
    from tradingagents.sensing.embeddings import MockEmbedder
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await ensure_consumer_group(r, stream="ingest:raw", group="triage")
    env = Envelope(source="rss",
                   ingested_ts=datetime.now(timezone.utc).isoformat(),
                   external_id="x:1", text="hello", source_tags={}, raw_path="")
    await r.xadd("ingest:raw", env.to_redis_fields())

    t = Triage(conn=conn, redis=r, embedder=MockEmbedder(), llm_call=_llm(),
                data_dir=str(tmp_path / "data"))
    await t.consume_once(group="triage", consumer="c1",
                          stream="ingest:raw", block_ms=10, batch=10)

    n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert n == 1
    pending = await r.xpending("ingest:raw", "triage")
    assert pending["pending"] == 0


@pytest.mark.unit
async def test_dead_letter_after_max_failures(conn, tmp_path):
    """A consistently-failing envelope ends up on ingest:dead.

    Note: XREADGROUP `>` only returns new messages; re-delivery requires
    XCLAIM or a `0` re-read. The triage in production pairs ``consume_once``
    with the periodic ``dead_letter_sweep`` (here called directly with
    ``max_deliveries=1`` so a single failure qualifies — minimum threshold).
    """
    from tradingagents.sensing.triage import Triage, dead_letter_sweep
    from tradingagents.sensing.embeddings import MockEmbedder
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await ensure_consumer_group(r, stream="ingest:raw", group="triage")

    await r.xadd("ingest:raw", {"data": "not-json-at-all"})

    t = Triage(conn=conn, redis=r, embedder=MockEmbedder(), llm_call=_llm(),
                data_dir=str(tmp_path / "data"))
    # One failed read leaves the entry on the PEL with times_delivered=1.
    await t.consume_once(group="triage", consumer="c1",
                          stream="ingest:raw", block_ms=10, batch=10)

    moved = await dead_letter_sweep(
        r, src_stream="ingest:raw", group="triage",
        dead_stream="ingest:dead", max_deliveries=1,
    )
    assert moved == 1
    dead = await r.xrange("ingest:dead")
    assert len(dead) == 1
