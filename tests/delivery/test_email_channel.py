from unittest.mock import MagicMock, patch
import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


@pytest.mark.unit
def test_email_outbound_uses_smtplib_and_records_message_id(tmp_path):
    from tradingagents.delivery.email import EmailOutbound

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r1"],
    )
    cfg = {
        "delivery": {"quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"},
                     "digest_modes": {"email": "full"}},
        "smtp": {"enabled": True, "host": "smtp.gmail.com", "port": 587,
                 "from_addr": "watter008@gmail.com", "to_addrs": ["watter008@gmail.com"]},
    }
    fake_smtp = MagicMock()
    with patch("smtplib.SMTP", return_value=fake_smtp) as smtp_ctor, \
         patch.dict("os.environ", {"IIC_SMTP_USER": "u", "IIC_SMTP_APP_PASSWORD": "p"}):
        ch = EmailOutbound(conn=conn, config=cfg)
        delivery_id = ch.send(brief={"brief_id": "b1", "mode": "deep_dive"},
                              mode="deep_dive", body="<html>BODY</html>")

    smtp_ctor.assert_called_once_with("smtp.gmail.com", 587, timeout=30)
    fake_smtp.starttls.assert_called_once()
    fake_smtp.login.assert_called_once_with("u", "p")
    fake_smtp.send_message.assert_called_once()
    sent_msg = fake_smtp.send_message.call_args[0][0]
    assert sent_msg["From"] == "watter008@gmail.com"
    assert sent_msg["To"] == "watter008@gmail.com"

    row = conn.execute(
        "SELECT channel, status, channel_ref FROM deliveries WHERE delivery_id = ?",
        (delivery_id,),
    ).fetchone()
    assert row[0] == "email"
    assert row[1] == "sent"
    assert row[2] is not None


@pytest.mark.unit
def test_email_outbound_disabled_records_skipped(tmp_path):
    from tradingagents.delivery.email import EmailOutbound

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r1"],
    )
    cfg = {
        "delivery": {"quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"},
                     "digest_modes": {"email": "full"}},
        "smtp": {"enabled": False, "host": "smtp.gmail.com", "port": 587,
                 "from_addr": "x@y", "to_addrs": ["x@y"]},
    }
    ch = EmailOutbound(conn=conn, config=cfg)
    delivery_id = ch.send(brief={"brief_id": "b1", "mode": "deep_dive"},
                          mode="deep_dive", body="...")
    row = conn.execute(
        "SELECT status, skip_reason FROM deliveries WHERE delivery_id = ?",
        (delivery_id,),
    ).fetchone()
    assert row[0] == "skipped"
    assert row[1] == "smtp_disabled"
