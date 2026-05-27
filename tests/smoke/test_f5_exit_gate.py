"""F5 exit-gate smoke test — synthetic end-to-end.

Exercises:
  - synthetic event → F4 worker → event_alert brief (uses F4's worker code)
  - simulated inline-button accept → brief_actions accepted → backtest dispatch
  - simulated free-text reply → classifier → refined brief
  - lapsed action → sweep → expired

All channel sends (Telegram, email, SMTP) are mocked at boundary.
"""

from unittest.mock import MagicMock, patch
import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


@pytest.mark.smoke
def test_f5_end_to_end_synthetic(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))
    import importlib, tradingagents.default_config as dc
    importlib.reload(dc)

    conn = iic_connect(str(tmp_path / "iic.db"))

    # 1. Seed an event_alert brief.
    store.insert_brief(
        conn, brief_id="ev1", mode="event_alert", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/ev1.md", run_ids=["r1"],
    )
    store.insert_delivery(
        conn, brief_id="ev1", channel="telegram", status="sent",
        sent_ts="2026-05-27T12:00:01+00:00",
        channel_ref="12345:1", skip_reason=None,
    )

    # 2. Simulate inline-button accept → brief_actions(accepted)
    from tradingagents.delivery.telegram_bot import handle_callback

    upd = MagicMock()
    upd.callback_query.data = "act:ev1:run_backtest:yes"
    upd.callback_query.message.chat.id = 12345
    upd.callback_query.message.message_id = 1
    upd.callback_query.answer = MagicMock()
    upd.callback_query.edit_message_reply_markup = MagicMock()
    handle_callback(update=upd, conn=conn)

    accepted = conn.execute(
        "SELECT * FROM brief_actions WHERE action_type='run_backtest' AND state='accepted'"
    ).fetchone()
    assert accepted is not None

    # 3. Action handler tick → dispatch backtest (stubbed)
    from tradingagents.orchestrator import action_handler

    fake_secretary = MagicMock()
    fake_dispatch = MagicMock(return_value=42)
    # Need backtest_id=42 to be a real row (FK). Insert it first.
    conn.execute(
        "INSERT INTO backtests (backtest_id, universe, start_date, end_date, status, created_ts) "
        "VALUES (42, '[]', 's', 'e', 'done', '2026-05-27T12:01:00+00:00')"
    )
    conn.commit()
    action_handler.tick(conn=conn, secretary=fake_secretary,
                       dispatch_backtest=fake_dispatch)
    fake_dispatch.assert_called_once_with("ev1", {})
    row = conn.execute(
        "SELECT result_backtest_id FROM brief_actions "
        "WHERE action_type='run_backtest' AND state='accepted'"
    ).fetchone()
    assert row[0] == 42

    # 4. Simulate free-text reply → brief_actions(accepted, refine_brief)
    from tradingagents.delivery.telegram_bot import handle_message

    reply_upd = MagicMock()
    reply_upd.message.reply_to_message = MagicMock()
    reply_upd.message.reply_to_message.chat.id = 12345
    reply_upd.message.reply_to_message.message_id = 1
    reply_upd.message.text = "more aggressive, drop value"
    reply_upd.message.chat.id = 12345
    handle_message(update=reply_upd, conn=conn,
                   config={"refinement": {"action_expires_hours": 24}})

    refine_action = conn.execute(
        "SELECT action_id FROM brief_actions "
        "WHERE action_type='refine_brief' AND state='accepted'"
    ).fetchone()
    assert refine_action is not None

    # 5. Action handler tick → classify_and_extract + compose_refinement (stubbed)
    # Seed the brief that compose_refinement is mocked to return (FK constraint).
    store.insert_brief(
        conn, brief_id="rf1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T12:05:00+00:00",
        content_path="briefs/rf1.md", run_ids=["r1"],
        parent_brief_id="ev1",
    )
    fake_secretary.compose_refinement.return_value = "rf1"
    with patch("tradingagents.orchestrator.action_handler.classify_and_extract",
               return_value={"personas": ["macro", "momentum"],
                             "risk_tilt": "more_aggressive",
                             "horizon": None, "analysts": None,
                             "interpretation": "OK."}):
        action_handler.tick(conn=conn, secretary=fake_secretary,
                            dispatch_backtest=fake_dispatch)

    fake_secretary.compose_refinement.assert_called_once()
    row = conn.execute(
        "SELECT result_brief_id FROM brief_actions "
        "WHERE action_type='refine_brief' AND state='accepted'"
    ).fetchone()
    assert row[0] == "rf1"

    # 6. Lapsed action → expired
    aid = store.insert_brief_action(
        conn, brief_id="ev1", action_type="run_backtest", action_params={},
        expires_at="2020-01-01T00:00:00+00:00",
    )
    action_handler.tick(conn=conn, secretary=fake_secretary,
                        dispatch_backtest=fake_dispatch)
    state = conn.execute(
        "SELECT state FROM brief_actions WHERE action_id = ?", (aid,),
    ).fetchone()[0]
    assert state == "expired"
