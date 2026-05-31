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
async def test_macro_cursor_jumps_to_max_no_reemit(conn, tmp_path, monkeypatch):
    """Regression: after a poll the FRED cursor must advance to the MAX
    release_id, not crawl forward one id at a time. FRED returns releases
    newest->oldest and EnvelopeWriter persists the cursor on every write, so
    without the post-loop max-persist the cursor would land on the SMALLEST
    emitted id and the next poll would re-emit all-but-one release every cycle
    (the 3525-duplicate staircase seen in the F3 soak)."""
    from tradingagents.sensing.adapters.macro import MacroAdapter
    monkeypatch.setenv("FRED_API_KEY", "fake")
    payload = {"releases": [                       # DESC, as sort_order=desc returns
        {"id": 100, "name": "Release 100", "link": "https://x/100"},
        {"id": 99,  "name": "Release 99",  "link": "https://x/99"},
        {"id": 98,  "name": "Release 98",  "link": "https://x/98"},
    ]}
    m = MagicMock(); m.json.return_value = payload; m.raise_for_status = lambda: None
    with patch("tradingagents.sensing.adapters.macro.requests.get", return_value=m):
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        a = MacroAdapter(staging_root=str(tmp_path / "s"), stream="ingest:raw")
        first = await a.poll_once(redis=r, conn=conn)
        second = await a.poll_once(redis=r, conn=conn)
    assert first == 3      # all three new on the first poll
    assert second == 0     # cursor jumped to 100 -> nothing new, no re-emit
    entries = await r.xrange("ingest:raw")
    assert len(entries) == 3   # not 3 + 2 (the off-by-one re-emit)


@pytest.mark.unit
async def test_macro_skips_when_fred_key_missing(conn, tmp_path, monkeypatch):
    from tradingagents.sensing.adapters.macro import MacroAdapter
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    a = MacroAdapter(staging_root=str(tmp_path / "s"), stream="ingest:raw")
    n = await a.poll_once(redis=r, conn=conn)
    assert n == 0
