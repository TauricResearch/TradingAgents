from unittest.mock import MagicMock, patch
import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


def _seed(conn, brief_id="b1"):
    store.insert_brief(
        conn, brief_id=brief_id, mode="event_alert", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path=f"briefs/{brief_id}.md", run_ids=["r1"],
    )


@pytest.mark.unit
def test_tick_expires_lapsed_pending_actions(tmp_path):
    from tradingagents.orchestrator.action_handler import tick

    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed(conn)
    aid = store.insert_brief_action(
        conn, brief_id="b1", action_type="run_backtest", action_params={},
        expires_at="2020-01-01T00:00:00+00:00",
    )
    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=MagicMock())
    row = conn.execute("SELECT state FROM brief_actions WHERE action_id = ?", (aid,)).fetchone()
    assert row[0] == "expired"


@pytest.mark.unit
def test_tick_dispatches_accepted_backtest(tmp_path):
    from tradingagents.orchestrator.action_handler import tick

    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed(conn)
    aid = store.insert_brief_action(
        conn, brief_id="b1", action_type="run_backtest", action_params={},
        expires_at="2099-01-01T00:00:00+00:00",
    )
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-05-27T12:30:00+00:00")

    fake_dispatch = MagicMock(return_value=99)
    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=fake_dispatch)
    fake_dispatch.assert_called_once_with("b1", {})
    row = conn.execute(
        "SELECT result_backtest_id FROM brief_actions WHERE action_id = ?", (aid,),
    ).fetchone()
    assert row[0] == 99


@pytest.mark.unit
def test_tick_dispatches_accepted_refinement(tmp_path):
    from tradingagents.orchestrator.action_handler import tick

    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed(conn)
    aid = store.insert_brief_action(
        conn, brief_id="b1", action_type="refine_brief",
        action_params={"reply_text": "more aggressive"},
        expires_at="2099-01-01T00:00:00+00:00",
    )
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-05-27T12:30:00+00:00")

    # Seed the brief that compose_refinement is mocked to return (FK constraint).
    store.insert_brief(
        conn, brief_id="b2_refined", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T13:00:00+00:00",
        content_path="briefs/b2_refined.md", run_ids=["rc"],
        parent_brief_id="b1",
    )
    fake_secretary = MagicMock()
    fake_secretary.compose_refinement.return_value = "b2_refined"
    with patch("tradingagents.orchestrator.action_handler.classify_and_extract",
               return_value={"personas": None, "risk_tilt": "more_aggressive",
                             "horizon": None, "analysts": None,
                             "interpretation": "OK."}):
        tick(conn=conn, secretary=fake_secretary, dispatch_backtest=MagicMock())

    fake_secretary.compose_refinement.assert_called_once()
    row = conn.execute(
        "SELECT result_brief_id FROM brief_actions WHERE action_id = ?", (aid,),
    ).fetchone()
    assert row[0] == "b2_refined"


@pytest.mark.unit
def test_tick_is_idempotent_on_completed_actions(tmp_path):
    from tradingagents.orchestrator.action_handler import tick

    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed(conn)
    aid = store.insert_brief_action(
        conn, brief_id="b1", action_type="run_backtest", action_params={},
        expires_at="2099-01-01T00:00:00+00:00",
    )
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-05-27T12:30:00+00:00")

    fake_dispatch = MagicMock(return_value=99)
    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=fake_dispatch)
    tick(conn=conn, secretary=MagicMock(), dispatch_backtest=fake_dispatch)
    assert fake_dispatch.call_count == 1


@pytest.mark.unit
def test_tick_handles_depth_exceeded_gracefully(tmp_path):
    from tradingagents.orchestrator.action_handler import tick
    from tradingagents.secretary.service import RefinementDepthExceeded

    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed(conn)
    aid = store.insert_brief_action(
        conn, brief_id="b1", action_type="refine_brief",
        action_params={"reply_text": "again"},
        expires_at="2099-01-01T00:00:00+00:00",
    )
    store.update_action_state(conn, action_id=aid, state="accepted",
                              responded_at="2026-05-27T12:30:00+00:00")

    fake_secretary = MagicMock()
    fake_secretary.compose_refinement.side_effect = RefinementDepthExceeded("depth")

    with patch("tradingagents.orchestrator.action_handler.classify_and_extract",
               return_value={"personas": None, "risk_tilt": None,
                             "horizon": None, "analysts": None, "interpretation": ""}):
        tick(conn=conn, secretary=fake_secretary, dispatch_backtest=MagicMock())

    assert True  # No exception leaked
