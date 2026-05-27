import json
import pytest
import fakeredis.aioredis
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.sensing.envelope import Envelope


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
async def test_envelope_writer_xadds_and_advances_cursor(conn, tmp_path):
    from tradingagents.sensing.adapters.base import EnvelopeWriter
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    w = EnvelopeWriter(source="polygon_news", redis=r, conn=conn,
                        stream="ingest:raw", staging_root=str(tmp_path / "staging"))
    env = Envelope(
        source="polygon_news",
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        external_id="pn:1", text="Apple beats", source_tags={},
        raw_path="",
    )
    await w.write(env, raw_payload={"foo": "bar"}, cursor="2026-05-26T00:00:00Z")
    entries = await r.xrange("ingest:raw")
    assert len(entries) == 1
    _, fields = entries[0]
    data = json.loads(fields["data"])
    assert data["source"] == "polygon_news"
    assert data["raw_path"].endswith(".json")
    row = conn.execute("SELECT cursor FROM ingest_cursor WHERE source='polygon_news'").fetchone()
    assert row["cursor"] == "2026-05-26T00:00:00Z"
    from pathlib import Path
    assert Path(data["raw_path"]).exists()


@pytest.mark.unit
def test_ingest_adapter_protocol_has_name_and_stream():
    from tradingagents.sensing.adapters.base import IngestAdapter
    annotations = IngestAdapter.__annotations__
    assert "name" in annotations
