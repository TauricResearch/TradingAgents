import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


@pytest.mark.unit
def test_fetch_recent_briefs_returns_newest_first(tmp_path):
    from tradingagents.dashboard.panels.briefs import fetch_recent_briefs

    conn = iic_connect(str(tmp_path / "iic.db"))
    for i, ts in enumerate(["2026-05-25T10:00", "2026-05-27T10:00", "2026-05-26T10:00"]):
        store.insert_brief(
            conn, brief_id=f"b{i}", mode="deep_dive", scope="AAPL",
            generated_ts=ts + ":00+00:00", content_path=f"briefs/b{i}.md", run_ids=["r"],
        )
    rows = fetch_recent_briefs(conn, limit=10)
    assert [r["brief_id"] for r in rows] == ["b1", "b2", "b0"]


@pytest.mark.unit
def test_fetch_recent_briefs_includes_delivery_status(tmp_path):
    from tradingagents.dashboard.panels.briefs import fetch_recent_briefs

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T10:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r"],
    )
    store.insert_delivery(
        conn, brief_id="b1", channel="cli", status="sent",
        sent_ts="2026-05-27T10:00:01+00:00", channel_ref="cli", skip_reason=None,
    )
    rows = fetch_recent_briefs(conn, limit=10)
    assert rows[0]["delivery_status"] == "sent"
    assert rows[0]["delivery_channel"] == "cli"


@pytest.mark.unit
def test_fetch_brief_thread_follows_parent_chain(tmp_path):
    from tradingagents.dashboard.panels.briefs import fetch_brief_thread

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T10:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r"],
    )
    store.insert_brief(
        conn, brief_id="b2", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T10:30:00+00:00",
        content_path="briefs/b2.md", run_ids=["r"], parent_brief_id="b1",
    )
    store.insert_brief(
        conn, brief_id="b3", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T11:00:00+00:00",
        content_path="briefs/b3.md", run_ids=["r"], parent_brief_id="b2",
    )
    thread = fetch_brief_thread(conn, brief_id="b3")
    assert [b["brief_id"] for b in thread] == ["b1", "b2", "b3"]
