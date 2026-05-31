import sqlite3
from datetime import time
from unittest.mock import patch

import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


@pytest.mark.unit
def test_base_send_event_alert_during_quiet_hours_skips(tmp_path):
    from tradingagents.delivery.base import DeliveryChannel

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="event_alert", scope="AAPL",
        generated_ts="2026-05-27T23:30:00+00:00",
        content_path="briefs/b1.md", run_ids=["r1"],
    )

    class Stub(DeliveryChannel):
        channel_name = "cli"
        def _send_impl(self, brief, mode, body):
            raise AssertionError("send_impl called during quiet hours")

    cfg = {
        "delivery": {
            "quiet_hours": {"enabled": True, "start": "22:00", "end": "07:00"},
            "digest_modes": {"cli": "full"},
        },
    }

    with patch("tradingagents.delivery.base._local_now",
               return_value=time(23, 30)):
        ch = Stub(conn=conn, config=cfg)
        delivery_id = ch.send(brief={"brief_id": "b1", "mode": "event_alert"},
                              mode="event_alert", body="...")

    row = conn.execute(
        "SELECT status, skip_reason FROM deliveries WHERE delivery_id = ?",
        (delivery_id,),
    ).fetchone()
    assert row[0] == "skipped"
    assert row[1] == "quiet_hours"


@pytest.mark.unit
def test_base_send_morning_digest_bypasses_quiet_hours(tmp_path):
    from tradingagents.delivery.base import DeliveryChannel

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b2", mode="morning_digest", scope='["AAPL"]',
        generated_ts="2026-05-27T23:30:00+00:00",
        content_path="briefs/b2.md", run_ids=["r1"],
    )

    captured = {}

    class Stub(DeliveryChannel):
        channel_name = "cli"
        def _send_impl(self, brief, mode, body):
            captured["called"] = True
            return ("cli", None)

    cfg = {
        "delivery": {
            "quiet_hours": {"enabled": True, "start": "22:00", "end": "07:00"},
            "digest_modes": {"cli": "full"},
        },
    }

    with patch("tradingagents.delivery.base._local_now",
               return_value=time(23, 30)):
        ch = Stub(conn=conn, config=cfg)
        ch.send(brief={"brief_id": "b2", "mode": "morning_digest"},
                mode="morning_digest", body="...")
    assert captured.get("called") is True


@pytest.mark.unit
def test_base_send_failure_recorded(tmp_path):
    from tradingagents.delivery.base import DeliveryChannel

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b3", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/b3.md", run_ids=["r1"],
    )

    class FailingStub(DeliveryChannel):
        channel_name = "email"
        def _send_impl(self, brief, mode, body):
            raise RuntimeError("smtp down")

    cfg = {"delivery": {"quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"},
                        "digest_modes": {"email": "full"}}}
    ch = FailingStub(conn=conn, config=cfg)
    delivery_id = ch.send(brief={"brief_id": "b3", "mode": "deep_dive"},
                          mode="deep_dive", body="...")
    row = conn.execute(
        "SELECT status, skip_reason, channel_ref FROM deliveries WHERE delivery_id = ?",
        (delivery_id,),
    ).fetchone()
    assert row[0] == "failed"
    assert row[1] is None
    assert "smtp down" in (row[2] or "")
