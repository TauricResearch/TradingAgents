import json
import pytest
import fakeredis.aioredis
from unittest.mock import patch, MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
async def test_macro_fred_emits_release(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters.macro import MacroAdapter
    monkeypatch.setenv("FRED_API_KEY", "fake")
    payload = {
        "releases": [{
            "id": 9, "name": "Employment Situation",
            "press_release": True, "link": "https://x",
            "realtime_start": "2026-05-26"}],
    }
    m = MagicMock(); m.json.return_value = payload; m.raise_for_status = lambda: None
    with patch("tradingagents.sensing.adapters.macro.requests.get", return_value=m):
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        a = MacroAdapter(staging_root=str(tmp_path / "s"), stream="ingest:raw")
        n = await a.poll_once(redis=r, conn=conn)
    assert n >= 1
    entries = await r.xrange("ingest:raw")
    env = json.loads(entries[0][1]["data"])
    assert env["source"] == "macro"
    assert "Employment Situation" in env["text"]


@pytest.mark.unit
async def test_macro_skips_when_fred_key_missing(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters.macro import MacroAdapter
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    a = MacroAdapter(staging_root=str(tmp_path / "s"), stream="ingest:raw")
    n = await a.poll_once(redis=r, conn=conn)
    assert n == 0
