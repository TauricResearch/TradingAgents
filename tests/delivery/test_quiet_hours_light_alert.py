from datetime import time
from unittest.mock import patch

from tradingagents.delivery.base import DeliveryChannel
from tradingagents.persistence.db import connect
from tradingagents.persistence import store


class FakeChannel(DeliveryChannel):
    channel_name = "fake"

    def _send_impl(self, brief, mode, body):
        return ("fake:1", None)


def test_light_alert_respects_quiet_hours(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn,
        brief_id="light1",
        mode="event_alert_light",
        scope='["NVDA"]',
        generated_ts="2026-06-01T04:00:00+00:00",
        content_path="briefs/light1.md",
        run_ids=[],
    )
    ch = FakeChannel(
        conn=conn,
        config={
            "delivery": {
                "quiet_hours": {
                    "enabled": True,
                    "start": "22:00",
                    "end": "07:00",
                }
            },
            "brief_action_ttl_hours": 24,
        },
    )
    with patch("tradingagents.delivery.base._local_now") as now:
        now.return_value = time(23, 0)
        delivery_id = ch.send(
            brief={"brief_id": "light1"},
            mode="event_alert_light",
            body="body",
        )
    row = conn.execute(
        "SELECT * FROM deliveries WHERE delivery_id = ?", (delivery_id,),
    ).fetchone()
    assert row["status"] == "skipped"
    assert row["skip_reason"] == "quiet_hours"
