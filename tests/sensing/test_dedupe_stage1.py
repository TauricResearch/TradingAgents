import pytest
import fakeredis.aioredis
from datetime import datetime, timezone

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


def _env(text="Apple beats", ext_id="pn:1", source="polygon_news"):
    from tradingagents.sensing.envelope import Envelope
    return Envelope(
        source=source,
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        external_id=ext_id,
        text=text,
        source_tags={},
        raw_path="data/events/staging/x.json",
    )


@pytest.mark.unit
async def test_stage1_first_event_not_duplicate(conn):
    from tradingagents.sensing.dedupe import DedupeStage1
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    ds1 = DedupeStage1(conn=conn, redis=r, fingerprint_ttl_hours=72)
    hit = await ds1.check(_env())
    assert hit is None


@pytest.mark.unit
async def test_stage1_repeat_external_id_is_duplicate(conn):
    from tradingagents.sensing.dedupe import DedupeStage1
    from tradingagents.persistence.store import insert_event
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    ds1 = DedupeStage1(conn=conn, redis=r, fingerprint_ttl_hours=72)
    insert_event(conn, event_id="ev-1", source="polygon_news",
                 ingested_ts=datetime.now(timezone.utc).isoformat(),
                 salience=0.5, raw_path="p", status="triaged", deduped_of=None)
    env = _env(ext_id="pn:42")
    await ds1.record(env, event_id="ev-1")
    hit = await ds1.check(_env(text="totally different", ext_id="pn:42"))
    assert hit == "ev-1"


@pytest.mark.unit
async def test_stage1_repeat_text_is_duplicate(conn):
    from tradingagents.sensing.dedupe import DedupeStage1
    from tradingagents.persistence.store import insert_event
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    ds1 = DedupeStage1(conn=conn, redis=r, fingerprint_ttl_hours=72)
    insert_event(conn, event_id="ev-1", source="polygon_news",
                 ingested_ts=datetime.now(timezone.utc).isoformat(),
                 salience=0.5, raw_path="p", status="triaged", deduped_of=None)
    await ds1.record(_env(text="Apple beats earnings"), event_id="ev-1")
    hit = await ds1.check(_env(text="apple beats   earnings", ext_id="pn:other"))
    assert hit == "ev-1"


@pytest.mark.unit
async def test_stage1_redis_hot_path_populated(conn):
    """If record() ran, SISMEMBER on the SHA set should return True."""
    from tradingagents.sensing.dedupe import DedupeStage1, _fp
    from tradingagents.persistence.store import insert_event
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    ds1 = DedupeStage1(conn=conn, redis=r, fingerprint_ttl_hours=72)
    insert_event(conn, event_id="ev-1", source="polygon_news",
                 ingested_ts=datetime.now(timezone.utc).isoformat(),
                 salience=0.5, raw_path="p", status="triaged", deduped_of=None)
    env = _env(text="foo")
    await ds1.record(env, event_id="ev-1")
    assert await r.sismember(ds1._sha_key(), _fp(env.text))
