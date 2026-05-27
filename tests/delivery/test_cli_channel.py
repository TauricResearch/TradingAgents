import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


@pytest.mark.unit
def test_cli_outbound_prints_body_and_records_delivery(tmp_path, capsys):
    from tradingagents.delivery.cli import CLIOutbound

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_brief(
        conn, brief_id="b1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-27T12:00:00+00:00",
        content_path="briefs/b1.md", run_ids=["r1"],
    )
    cfg = {"delivery": {"quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"},
                        "digest_modes": {"cli": "full"}}}
    ch = CLIOutbound(conn=conn, config=cfg)
    delivery_id = ch.send(brief={"brief_id": "b1", "mode": "deep_dive"},
                          mode="deep_dive", body="HELLO BODY")
    captured = capsys.readouterr()
    assert "HELLO BODY" in captured.out

    row = conn.execute(
        "SELECT channel, status, channel_ref FROM deliveries WHERE delivery_id = ?",
        (delivery_id,),
    ).fetchone()
    assert row[0] == "cli"
    assert row[1] == "sent"
    assert row[2] == "cli"
