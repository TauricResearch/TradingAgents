from pathlib import Path

from tradingagents.analysis_pack.store import create_analysis_pack, load_analysis_pack
from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def test_create_and_load_analysis_pack(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_event(
        conn,
        event_id="ev1",
        source="rss",
        ingested_ts="2026-06-01T00:00:00+00:00",
        salience=0.9,
        raw_path=None,
        status="triaged",
        deduped_of=None,
    )
    data_dir = tmp_path / "data"
    pack_id = create_analysis_pack(
        conn=conn,
        data_dir=data_dir,
        event_id="ev1",
        ticker="NVDA",
        trade_date="2026-06-01",
        source_run_ids=["r1"],
        content={"ticker": "NVDA", "facts": ["guidance raised"]},
    )

    loaded = load_analysis_pack(conn=conn, data_dir=data_dir, pack_id=pack_id)
    assert loaded["event_id"] == "ev1"
    assert loaded["ticker"] == "NVDA"
    assert loaded["content"]["facts"] == ["guidance raised"]
    assert Path(data_dir / loaded["content_path"]).exists()
