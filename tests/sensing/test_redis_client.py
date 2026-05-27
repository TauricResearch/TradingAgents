import pytest
import fakeredis.aioredis


@pytest.mark.unit
async def test_ensure_consumer_group_creates_when_missing():
    from tradingagents.sensing.redis_client import ensure_consumer_group
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await ensure_consumer_group(r, stream="ingest:raw", group="triage")
    info = await r.xinfo_groups("ingest:raw")
    assert any(g["name"] == "triage" for g in info)


@pytest.mark.unit
async def test_ensure_consumer_group_tolerates_already_exists():
    from tradingagents.sensing.redis_client import ensure_consumer_group
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await ensure_consumer_group(r, stream="s", group="g")
    # Second call must not raise.
    await ensure_consumer_group(r, stream="s", group="g")
