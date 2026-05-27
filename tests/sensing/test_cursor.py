import pytest
from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
def test_cursor_get_missing_returns_none(conn):
    from tradingagents.sensing.cursor import CursorStore
    cs = CursorStore(conn)
    assert cs.get("polygon_news") is None


@pytest.mark.unit
def test_cursor_set_and_get(conn):
    from tradingagents.sensing.cursor import CursorStore
    cs = CursorStore(conn)
    cs.set("polygon_news", "2026-05-26T14:00:00Z")
    assert cs.get("polygon_news") == "2026-05-26T14:00:00Z"


@pytest.mark.unit
def test_cursor_set_overwrites(conn):
    from tradingagents.sensing.cursor import CursorStore
    cs = CursorStore(conn)
    cs.set("rss", "a")
    cs.set("rss", "b")
    assert cs.get("rss") == "b"


@pytest.mark.unit
def test_cursor_updated_ts_advances(conn):
    import time
    from tradingagents.sensing.cursor import CursorStore
    cs = CursorStore(conn)
    cs.set("x", "1")
    t1 = conn.execute("SELECT updated_ts FROM ingest_cursor WHERE source='x'").fetchone()[0]
    time.sleep(0.01)
    cs.set("x", "2")
    t2 = conn.execute("SELECT updated_ts FROM ingest_cursor WHERE source='x'").fetchone()[0]
    assert t2 > t1
