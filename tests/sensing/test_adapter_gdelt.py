import json
import pytest
import fakeredis.aioredis
from unittest.mock import patch, MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
async def test_gdelt_emits_envelope(conn, tmp_path):
    from tradingagents.sensing.adapters.gdelt import GdeltAdapter
    payload = {
        "articles": [{
            "url": "https://news.example/g-1",
            "title": "Macro shock",
            "seendate": "20260526T140000Z",
            "domain": "news.example",
        }],
    }
    m = MagicMock(); m.json.return_value = payload; m.raise_for_status = lambda: None
    with patch("tradingagents.sensing.adapters.gdelt.requests.get", return_value=m):
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        a = GdeltAdapter(query="earnings", staging_root=str(tmp_path / "s"),
                          stream="ingest:raw")
        n = await a.poll_once(redis=r, conn=conn)
    assert n == 1
    entries = await r.xrange("ingest:raw")
    env = json.loads(entries[0][1]["data"])
    assert env["source"] == "gdelt"
    assert env["external_id"] == "gdelt:https://news.example/g-1"
    assert "Macro shock" in env["text"]
