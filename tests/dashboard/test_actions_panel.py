import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


def _seed(conn, brief_id="b1"):
    store.insert_brief(
        conn, brief_id=brief_id, mode="event_alert", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path=f"briefs/{brief_id}.md", run_ids=["r"],
    )


@pytest.mark.unit
def test_fetch_pending_actions(tmp_path):
    from tradingagents.dashboard.panels.actions import fetch_pending_actions

    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed(conn)
    aid = store.insert_brief_action(
        conn, brief_id="b1", action_type="run_backtest", action_params={},
        expires_at="2099-01-01T00:00:00+00:00",
    )
    rows = fetch_pending_actions(conn)
    assert len(rows) == 1
    assert rows[0]["action_id"] == aid


@pytest.mark.unit
def test_fetch_recent_actioned(tmp_path):
    from tradingagents.dashboard.panels.actions import fetch_recent_actioned

    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed(conn)
    aid = store.insert_brief_action(
        conn, brief_id="b1", action_type="run_backtest", action_params={},
        expires_at="2099-01-01T00:00:00+00:00",
    )
    store.update_action_state(conn, action_id=aid, state="expired",
                              responded_at="2026-05-27T15:00:00+00:00")
    rows = fetch_recent_actioned(conn, limit=20)
    assert len(rows) == 1
    assert rows[0]["state"] == "expired"
