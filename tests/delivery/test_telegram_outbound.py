from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


@pytest.mark.unit
def test_telegram_outbound_sends_with_inline_keyboard_for_event_alert(tmp_path):
    from tradingagents.delivery.telegram import TelegramOutbound

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="event_alert", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r1"],
    )
    cfg = {
        "delivery": {"quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"},
                     "digest_modes": {"telegram": "terse"}},
        "telegram_bot": {"enabled": True, "allowed_chat_ids": [12345],
                         "poll_interval_seconds": 1},
    }
    fake_sent = MagicMock(message_id=678)
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock(return_value=fake_sent)
    with patch("tradingagents.delivery.telegram._get_bot", return_value=fake_bot), \
         patch.dict("os.environ", {"IIC_TELEGRAM_BOT_TOKEN": "tok"}):
        ch = TelegramOutbound(conn=conn, config=cfg)
        delivery_id = ch.send(brief={"brief_id": "b1", "mode": "event_alert"},
                              mode="event_alert", body="ALERT TEXT")
    args, kwargs = fake_bot.send_message.call_args
    assert kwargs["chat_id"] == 12345
    assert "ALERT TEXT" in kwargs["text"]
    assert kwargs.get("reply_markup") is not None
    row = conn.execute(
        "SELECT channel, status, channel_ref FROM deliveries WHERE delivery_id = ?",
        (delivery_id,),
    ).fetchone()
    assert row[0] == "telegram"
    assert row[1] == "sent"
    assert row[2] == "12345:678"


@pytest.mark.unit
def test_telegram_outbound_no_keyboard_for_morning_digest(tmp_path):
    from tradingagents.delivery.telegram import TelegramOutbound

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b2", mode="morning_digest", scope='["AAPL"]',
        generated_ts="2026-05-27T07:00:00+00:00",
        content_path="briefs/b2.md", run_ids=["r1"],
    )
    cfg = {
        "delivery": {"quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"},
                     "digest_modes": {"telegram": "terse"}},
        "telegram_bot": {"enabled": True, "allowed_chat_ids": [12345],
                         "poll_interval_seconds": 1},
    }
    fake_sent = MagicMock(message_id=679)
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock(return_value=fake_sent)
    with patch("tradingagents.delivery.telegram._get_bot", return_value=fake_bot), \
         patch.dict("os.environ", {"IIC_TELEGRAM_BOT_TOKEN": "tok"}):
        ch = TelegramOutbound(conn=conn, config=cfg)
        ch.send(brief={"brief_id": "b2", "mode": "morning_digest"},
                mode="morning_digest", body="DIGEST TEXT")
    kwargs = fake_bot.send_message.call_args.kwargs
    assert kwargs.get("reply_markup") is None


@pytest.mark.unit
def test_telegram_outbound_disabled_records_skipped(tmp_path):
    from tradingagents.delivery.telegram import TelegramOutbound

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="event_alert", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r1"],
    )
    cfg = {
        "delivery": {"quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"},
                     "digest_modes": {"telegram": "terse"}},
        "telegram_bot": {"enabled": False, "allowed_chat_ids": [],
                         "poll_interval_seconds": 1},
    }
    ch = TelegramOutbound(conn=conn, config=cfg)
    delivery_id = ch.send(brief={"brief_id": "b1", "mode": "event_alert"},
                          mode="event_alert", body="...")
    row = conn.execute(
        "SELECT status, skip_reason FROM deliveries WHERE delivery_id = ?",
        (delivery_id,),
    ).fetchone()
    assert row[0] == "skipped"
    assert row[1] == "telegram_disabled"
