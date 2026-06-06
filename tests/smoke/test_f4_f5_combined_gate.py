from datetime import datetime, timezone

from tests.scripts.test_f4_f5_exit_gate import seed_combined_flow
from tradingagents.persistence.db import connect


def test_f4_f5_combined_gate_smoke(tmp_path):
    from scripts.f4_f5_exit_gate import evaluate

    conn = connect(str(tmp_path / "iic.db"))
    seed_combined_flow(conn)

    report = evaluate(
        conn,
        since=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        window_hours=1,
    )

    assert report["pass"] is True
    assert set(report["checks"]) >= {
        "light_alert_latency",
        "light_delivery_audit",
        "alert_quality_audit",
        "approval_lineage",
        "worker_errors",
        "full_brief_delivery",
    }
