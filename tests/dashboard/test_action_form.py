import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


@pytest.mark.unit
def test_submit_refinement_writes_action(tmp_path):
    from tradingagents.dashboard.action_form import submit_refinement

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r"],
    )
    aid = submit_refinement(conn=conn, brief_id="b1", reply_text="more aggressive",
                            config={"refinement": {"action_expires_hours": 24}})
    row = conn.execute(
        "SELECT brief_id, action_type, state, action_params FROM brief_actions "
        "WHERE action_id = ?", (aid,),
    ).fetchone()
    assert row[0] == "b1"
    assert row[1] == "refine_brief"
    assert row[2] == "accepted"
    import json as _j
    assert _j.loads(row[3])["reply_text"] == "more aggressive"


@pytest.mark.unit
def test_submit_backtest_writes_action(tmp_path):
    from tradingagents.dashboard.action_form import submit_backtest

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r"],
    )
    aid = submit_backtest(conn=conn, brief_id="b1",
                          config={"refinement": {"action_expires_hours": 24}})
    row = conn.execute(
        "SELECT action_type, state FROM brief_actions WHERE action_id = ?", (aid,),
    ).fetchone()
    assert row[0] == "run_backtest"
    assert row[1] == "accepted"


@pytest.mark.unit
def test_submit_refinement_rejects_empty(tmp_path):
    from tradingagents.dashboard.action_form import submit_refinement

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r"],
    )
    with pytest.raises(ValueError, match="empty"):
        submit_refinement(conn=conn, brief_id="b1", reply_text="   ",
                          config={"refinement": {"action_expires_hours": 24}})
