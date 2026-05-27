import sqlite3
import pytest

from tradingagents.persistence.db import connect as iic_connect


@pytest.mark.unit
def test_f5_schema_adds_columns(tmp_path):
    conn = iic_connect(str(tmp_path / "iic.db"))

    # deliveries.skip_reason + channel_ref
    cols = {row[1] for row in conn.execute("PRAGMA table_info(deliveries)").fetchall()}
    assert "skip_reason" in cols
    assert "channel_ref" in cols

    # briefs.refine_depth + refine_overrides
    cols = {row[1] for row in conn.execute("PRAGMA table_info(briefs)").fetchall()}
    assert "refine_depth" in cols
    assert "refine_overrides" in cols


@pytest.mark.unit
def test_f5_indexes_present(tmp_path):
    conn = iic_connect(str(tmp_path / "iic.db"))
    indexes = {row[1] for row in conn.execute(
        "SELECT type, name FROM sqlite_master WHERE type='index'"
    ).fetchall()}
    assert "idx_deliveries_brief" in indexes
    assert "idx_brief_actions_pending_expires" in indexes


@pytest.mark.unit
def test_schema_is_idempotent(tmp_path):
    # Calling connect twice on the same path must not raise duplicate-column.
    p = str(tmp_path / "iic.db")
    iic_connect(p)
    iic_connect(p)


from tradingagents.persistence import store


def _seed_brief(conn, brief_id="b1", mode="event_alert", parent=None, depth=0):
    store.insert_brief(
        conn,
        brief_id=brief_id,
        mode=mode,
        scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path=f"briefs/{brief_id}.md",
        run_ids=["r1"],
        parent_brief_id=parent,
    )
    if depth:
        conn.execute(
            "UPDATE briefs SET refine_depth = ? WHERE brief_id = ?",
            (depth, brief_id),
        )
        conn.commit()


@pytest.mark.unit
def test_insert_delivery_writes_row(tmp_path):
    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed_brief(conn)
    delivery_id = store.insert_delivery(
        conn,
        brief_id="b1",
        channel="cli",
        status="sent",
        sent_ts="2026-05-27T12:00:01+00:00",
        channel_ref="cli",
        skip_reason=None,
    )
    assert delivery_id == 1
    row = conn.execute(
        "SELECT channel, status, channel_ref, skip_reason FROM deliveries WHERE delivery_id = ?",
        (delivery_id,),
    ).fetchone()
    assert (row[0], row[1], row[2], row[3]) == ("cli", "sent", "cli", None)


@pytest.mark.unit
def test_insert_delivery_quiet_hours_skip(tmp_path):
    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed_brief(conn)
    store.insert_delivery(
        conn,
        brief_id="b1",
        channel="telegram",
        status="skipped",
        sent_ts=None,
        channel_ref=None,
        skip_reason="quiet_hours",
    )
    row = conn.execute("SELECT status, skip_reason FROM deliveries").fetchone()
    assert row[0] == "skipped"
    assert row[1] == "quiet_hours"


@pytest.mark.unit
def test_resolve_brief_id_by_channel_ref(tmp_path):
    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed_brief(conn)
    store.insert_delivery(
        conn, brief_id="b1", channel="telegram", status="sent",
        sent_ts="2026-05-27T12:00:00+00:00",
        channel_ref="12345:678", skip_reason=None,
    )
    assert store.resolve_brief_id_by_channel_ref(conn, channel="telegram",
                                                 channel_ref="12345:678") == "b1"
    assert store.resolve_brief_id_by_channel_ref(conn, channel="telegram",
                                                 channel_ref="missing") is None


@pytest.mark.unit
def test_brief_actions_pending_and_dispatch(tmp_path):
    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed_brief(conn)
    aid = store.insert_brief_action(
        conn, brief_id="b1", action_type="run_backtest",
        action_params={"strategies": []},
        expires_at="2026-05-28T12:00:00+00:00",
    )
    # Initially pending
    rows = store.fetch_actions(conn, state="pending")
    assert len(rows) == 1 and rows[0]["action_id"] == aid

    # Accept it
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-05-27T13:00:00+00:00")

    # Now no pending, one accepted-undispatched
    assert store.fetch_actions(conn, state="pending") == []
    accepted = store.fetch_accepted_undispatched(conn)
    assert len(accepted) == 1 and accepted[0]["action_id"] == aid

    # Mark done with result_backtest_id
    store.mark_action_done(conn, action_id=aid, result_backtest_id=42)
    assert store.fetch_accepted_undispatched(conn) == []


@pytest.mark.unit
def test_expire_lapsed_actions(tmp_path):
    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed_brief(conn)
    # Already past expires_at
    aid = store.insert_brief_action(
        conn, brief_id="b1", action_type="run_backtest", action_params={},
        expires_at="2020-01-01T00:00:00+00:00",
    )
    n = store.expire_lapsed_actions(conn)
    assert n == 1
    row = conn.execute("SELECT state FROM brief_actions WHERE action_id = ?", (aid,)).fetchone()
    assert row[0] == "expired"


@pytest.mark.unit
def test_load_brief_with_depth(tmp_path):
    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed_brief(conn, brief_id="b1", depth=2)
    b = store.load_brief(conn, "b1")
    assert b["brief_id"] == "b1"
    assert b["refine_depth"] == 2
    assert b["parent_brief_id"] is None
