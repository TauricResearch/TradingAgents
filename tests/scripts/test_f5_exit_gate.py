import json
from unittest.mock import patch
import pytest

from tradingagents.persistence.db import connect as iic_connect
from tradingagents.persistence import store


def _seed_passing_soak(conn):
    """Seed a DB that satisfies all G1–G6 checks."""
    # G1: 3 morning_digest deliveries
    for i in range(3):
        bid = f"mg{i}"
        store.insert_brief(
            conn, brief_id=bid, mode="morning_digest", scope='["AAPL"]',
            generated_ts=f"2026-05-2{5+i}T07:00:00+00:00",
            content_path=f"briefs/{bid}.md", run_ids=["r"],
        )
        store.insert_delivery(
            conn, brief_id=bid, channel="email", status="sent",
            sent_ts=f"2026-05-2{5+i}T07:00:01+00:00",
            channel_ref="<x>", skip_reason=None,
        )
    # G2: 1 event_alert delivered
    store.insert_brief(
        conn, brief_id="ev1", mode="event_alert", scope="AAPL",
        generated_ts="2026-05-26T14:00:00+00:00",
        content_path="briefs/ev1.md", run_ids=["r"],
    )
    store.insert_delivery(
        conn, brief_id="ev1", channel="telegram", status="sent",
        sent_ts="2026-05-26T14:00:01+00:00",
        channel_ref="12345:1", skip_reason=None,
    )
    # G3: 1 deep_dive delivered
    store.insert_brief(
        conn, brief_id="dd1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-26T15:00:00+00:00",
        content_path="briefs/dd1.md", run_ids=["r"],
    )
    store.insert_delivery(
        conn, brief_id="dd1", channel="cli", status="sent",
        sent_ts="2026-05-26T15:00:01+00:00",
        channel_ref="cli", skip_reason=None,
    )
    # G4: accepted backtest with result
    aid1 = store.insert_brief_action(
        conn, brief_id="ev1", action_type="run_backtest", action_params={},
        expires_at="2099-01-01T00:00:00+00:00",
    )
    store.update_action_state(conn, action_id=aid1, state="accepted",
                              responded_at="2026-05-26T14:01:00+00:00")
    conn.execute(
        "INSERT INTO backtests (universe, start_date, end_date, status, created_ts) "
        "VALUES ('[\"AAPL\"]', '2026-04-26', '2026-05-26', 'done', '2026-05-26T14:02:00+00:00')"
    )
    bt_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    store.mark_action_done(conn, action_id=aid1, result_backtest_id=bt_id)
    # G5: expired action
    aid2 = store.insert_brief_action(
        conn, brief_id="ev1", action_type="run_backtest", action_params={},
        expires_at="2020-01-01T00:00:00+00:00",
    )
    conn.execute(
        "UPDATE brief_actions SET state = 'expired' WHERE action_id = ?", (aid2,)
    )
    conn.commit()
    # G6: refined brief (parent + overrides)
    store.insert_brief(
        conn, brief_id="rf1", mode="deep_dive", scope="AAPL",
        generated_ts="2026-05-26T16:00:00+00:00",
        content_path="briefs/rf1.md", run_ids=["r"], parent_brief_id="dd1",
    )
    store.update_brief_refine_metadata(
        conn, brief_id="rf1", refine_depth=1,
        refine_overrides={"personas": ["macro"], "risk_tilt": None,
                          "horizon": None, "analysts": None, "interpretation": "ok"},
    )
    # G8: cost data
    store.insert_run(conn, run_id="rc1", ticker="AAPL", persona_id="macro",
                     started_ts="2026-05-25T07:00:00+00:00",
                     artifact_dir="runs/rc1")
    store.finalize_run(conn, run_id="rc1",
                       ended_ts="2026-05-25T07:05:00+00:00",
                       status="ok", decision="BUY", confidence=0.7)
    conn.execute(
        "INSERT INTO costs (run_id, provider, model, in_tokens, out_tokens, usd_estimate) "
        "VALUES ('rc1', 'deepseek', 'm', 1000, 500, 0.05)"
    )
    # Need data across 3 days for G8
    for i, ts in enumerate(["2026-05-25T07:00:00+00:00", "2026-05-26T07:00:00+00:00",
                            "2026-05-27T07:00:00+00:00"]):
        rid = f"rc-day{i}"
        store.insert_run(conn, run_id=rid, ticker="AAPL", persona_id="macro",
                         started_ts=ts, artifact_dir=f"runs/{rid}")
        store.finalize_run(conn, run_id=rid, ended_ts=ts, status="ok",
                           decision="BUY", confidence=0.7)
        conn.execute(
            "INSERT INTO costs (run_id, provider, model, in_tokens, out_tokens, usd_estimate) "
            "VALUES (?, 'deepseek', 'm', 1000, 500, 0.05)",
            (rid,),
        )
    conn.commit()


@pytest.mark.unit
def test_exit_gate_passes_with_full_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))
    import importlib, tradingagents.default_config as dc
    importlib.reload(dc)

    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed_passing_soak(conn)

    with patch("scripts.f5_exit_gate._check_no_restarts", return_value=(True, "no restarts")):
        from scripts.f5_exit_gate import evaluate
        report = evaluate(since="2026-05-25T00:00:00+00:00")
    assert report["pass"] is True
    for g in ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"):
        assert report["checks"][g]["pass"] is True, f"{g}: {report['checks'][g]}"


@pytest.mark.unit
def test_exit_gate_fails_when_no_refinement(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))
    import importlib, tradingagents.default_config as dc
    importlib.reload(dc)

    conn = iic_connect(str(tmp_path / "iic.db"))
    _seed_passing_soak(conn)
    # Remove the refinement
    conn.execute("DELETE FROM briefs WHERE brief_id = 'rf1'")
    conn.commit()

    with patch("scripts.f5_exit_gate._check_no_restarts", return_value=(True, "")):
        from scripts.f5_exit_gate import evaluate
        report = evaluate(since="2026-05-25T00:00:00+00:00")
    assert report["pass"] is False
    assert report["checks"]["G6"]["pass"] is False


@pytest.mark.unit
def test_event_alert_check_counts_light_alert_deliveries(tmp_path):
    from scripts.f5_exit_gate import _g2_event_alerts

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_event(
        conn,
        event_id="ev-light",
        source="rss",
        ingested_ts="2026-05-26T13:59:00+00:00",
        salience=0.9,
        raw_path=None,
        status="triaged",
        deduped_of=None,
    )
    store.insert_brief(
        conn,
        brief_id="light1",
        mode="event_alert_light",
        scope='["AAPL"]',
        generated_ts="2026-05-26T14:00:00+00:00",
        content_path="briefs/light1.md",
        run_ids=[],
        trigger_event_id="ev-light",
    )
    store.insert_delivery(
        conn,
        brief_id="light1",
        channel="telegram",
        status="sent",
        sent_ts="2026-05-26T14:00:01+00:00",
        channel_ref="12345:1",
        skip_reason=None,
    )

    ok, detail = _g2_event_alerts(conn, "2026-05-25T00:00:00+00:00")

    assert ok is True
    assert "1 event_alert/event_alert_light" in detail
