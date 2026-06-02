import pytest
from unittest.mock import AsyncMock, MagicMock
from tradingagents.persistence.db import connect
from tradingagents.persistence import store


@pytest.mark.unit
def test_light_alert_keyboard_has_per_ticker_buttons():
    pytest.importorskip("telegram")
    from tradingagents.delivery.telegram import _make_light_alert_keyboard

    kb = _make_light_alert_keyboard("lb1", ["NVDA", "PANW"])
    # Flatten all buttons and collect callback_data
    datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "act:lb1:run_full_study:NVDA" in datas
    assert "act:lb1:run_full_study:PANW" in datas
    assert "act:lb1:run_full_study:__all__" in datas
    assert "act:lb1:run_full_study:__dismiss__" in datas


@pytest.mark.unit
def test_light_alert_keyboard_odd_ticker_count_layout():
    pytest.importorskip("telegram")
    from tradingagents.delivery.telegram import _make_light_alert_keyboard

    kb = _make_light_alert_keyboard("lb1", ["NVDA", "PANW", "CRWD"])
    rows = kb.inline_keyboard
    # 3 tickers -> [2 buttons][1 button][all/dismiss row]
    assert len(rows) == 3
    assert len(rows[0]) == 2
    assert len(rows[1]) == 1
    assert rows[1][0].callback_data == "act:lb1:run_full_study:CRWD"
    # final row is the all/dismiss controls
    assert [b.callback_data for b in rows[2]] == [
        "act:lb1:run_full_study:__all__",
        "act:lb1:run_full_study:__dismiss__",
    ]


def _seed_light_with_delivery(conn, brief_id="lb1", channel_ref="12345:678"):
    store.insert_event(conn, event_id="ev1", source="test",
                       ingested_ts="2026-06-01T00:00:00+00:00",
                       salience=None, raw_path=None, status="processed",
                       deduped_of=None)
    store.insert_brief(conn, brief_id=brief_id, mode="event_alert_light",
                       scope='["NVDA", "PANW"]',
                       generated_ts="2026-06-01T00:00:00+00:00",
                       content_path=f"briefs/{brief_id}.md", run_ids=[],
                       trigger_event_id="ev1")
    store.insert_delivery(conn, brief_id=brief_id, channel="telegram",
                          status="sent", sent_ts="2026-06-01T00:00:01+00:00",
                          channel_ref=channel_ref, skip_reason=None)
    for t in ("NVDA", "PANW"):
        store.insert_brief_action(conn, brief_id=brief_id,
                                  action_type="run_full_study",
                                  action_params={"ticker": t},
                                  expires_at="2099-01-01T00:00:00+00:00")


def _callback(data):
    u = MagicMock()
    u.callback_query.data = data
    u.callback_query.message.chat.id = 12345
    u.callback_query.message.message_id = 678
    u.callback_query.answer = AsyncMock()
    return u


@pytest.mark.unit
def test_callback_accepts_single_ticker(tmp_path):
    from tradingagents.delivery.telegram_bot import handle_callback
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light_with_delivery(conn)
    handle_callback(update=_callback("act:lb1:run_full_study:NVDA"), conn=conn)
    states = dict(conn.execute(
        "SELECT json_extract(action_params,'$.ticker'), state "
        "FROM brief_actions").fetchall())
    assert states["NVDA"] == "accepted"
    assert states["PANW"] == "pending"


@pytest.mark.unit
def test_callback_study_all_accepts_every_pending(tmp_path):
    from tradingagents.delivery.telegram_bot import handle_callback
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light_with_delivery(conn)
    handle_callback(update=_callback("act:lb1:run_full_study:__all__"), conn=conn)
    states = [r[0] for r in conn.execute("SELECT state FROM brief_actions")]
    assert set(states) == {"accepted"}
    assert len(states) == 2


@pytest.mark.unit
def test_callback_dismiss_all_declines_every_pending(tmp_path):
    from tradingagents.delivery.telegram_bot import handle_callback
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light_with_delivery(conn)
    handle_callback(update=_callback("act:lb1:run_full_study:__dismiss__"), conn=conn)
    states = [r[0] for r in conn.execute("SELECT state FROM brief_actions")]
    assert set(states) == {"declined"}
    assert len(states) == 2


@pytest.mark.unit
def test_callback_single_ticker_is_idempotent(tmp_path):
    from tradingagents.delivery.telegram_bot import handle_callback
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light_with_delivery(conn)
    # two clicks on the same ticker
    handle_callback(update=_callback("act:lb1:run_full_study:NVDA"), conn=conn)
    handle_callback(update=_callback("act:lb1:run_full_study:NVDA"), conn=conn)
    states = dict(conn.execute(
        "SELECT json_extract(action_params,'$.ticker'), state "
        "FROM brief_actions").fetchall())
    assert states["NVDA"] == "accepted"
    assert states["PANW"] == "pending"


@pytest.mark.unit
def test_callback_unmatched_ticker_is_noop(tmp_path):
    from tradingagents.delivery.telegram_bot import handle_callback
    conn = connect(str(tmp_path / "iic.db"))
    _seed_light_with_delivery(conn)
    handle_callback(update=_callback("act:lb1:run_full_study:AAPL"), conn=conn)
    states = [r[0] for r in conn.execute("SELECT state FROM brief_actions")]
    assert set(states) == {"pending"}
