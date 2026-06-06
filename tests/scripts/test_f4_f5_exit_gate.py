from datetime import datetime, timezone

from tradingagents.persistence import store
from tradingagents.persistence.db import connect


def seed_combined_flow(conn):
    store.insert_event(
        conn,
        event_id="ev1",
        source="rss",
        ingested_ts="2026-06-01T00:00:00+00:00",
        salience=0.95,
        raw_path=None,
        status="triaged",
        deduped_of=None,
    )
    store.insert_alert_evaluation(
        conn,
        event_id="ev1",
        tickers=["NVDA"],
        decision="pass",
        score=0.91,
        payload={"rationale": "material, actionable catalyst"},
        created_ts="2026-06-01T00:00:30+00:00",
    )
    store.insert_brief(
        conn,
        brief_id="light1",
        mode="event_alert_light",
        scope='["NVDA"]',
        generated_ts="2026-06-01T00:02:00+00:00",
        content_path="briefs/light1.md",
        run_ids=[],
        trigger_event_id="ev1",
    )
    store.insert_delivery(
        conn,
        brief_id="light1",
        channel="telegram",
        status="sent",
        sent_ts="2026-06-01T00:02:01+00:00",
        channel_ref="1",
        skip_reason=None,
    )
    aid = store.insert_brief_action(
        conn,
        brief_id="light1",
        action_type="run_full_study",
        action_params={"ticker": "NVDA"},
        expires_at="2026-06-02T00:00:00+00:00",
    )
    store.update_action_state(
        conn,
        action_id=aid,
        state="accepted",
        responded_at="2026-06-01T00:03:00+00:00",
    )
    conn.execute(
        "INSERT INTO queue_jobs (job_id, job_type, payload, state, enqueued_ts, "
        "finished_ts, trigger_event_id) "
        "VALUES (7, 'event_alert', '{}', 'done', "
        "'2026-06-01T00:03:10+00:00', '2026-06-01T00:08:00+00:00', 'ev1')"
    )
    conn.commit()
    store.mark_action_dispatched(
        conn,
        action_id=aid,
        result_job_id=7,
        dispatched_ts="2026-06-01T00:03:10+00:00",
    )
    store.insert_run(
        conn,
        run_id="r1",
        ticker="NVDA",
        persona_id="balanced",
        started_ts="2026-06-01T00:04:00+00:00",
        artifact_dir="runs/r1",
    )
    store.finalize_run(
        conn,
        run_id="r1",
        ended_ts="2026-06-01T00:07:00+00:00",
        status="complete",
        decision="BUY",
    )
    store.record_cost(
        conn,
        run_id="r1",
        provider="deepseek",
        model="deepseek-chat",
        in_tokens=1000,
        out_tokens=200,
        usd_estimate=0.001,
        cache_hit_tokens=400,
        cache_miss_tokens=600,
    )
    store.insert_brief(
        conn,
        brief_id="full1",
        mode="event_alert",
        scope="NVDA",
        generated_ts="2026-06-01T00:08:00+00:00",
        content_path="briefs/full1.md",
        run_ids=["r1"],
        parent_brief_id="light1",
        trigger_event_id="ev1",
    )
    store.mark_action_done(conn, action_id=aid, result_brief_id="full1")
    store.insert_delivery(
        conn,
        brief_id="full1",
        channel="telegram",
        status="sent",
        sent_ts="2026-06-01T00:08:01+00:00",
        channel_ref="2",
        skip_reason=None,
    )


def test_combined_gate_passes_complete_approval_flow(tmp_path):
    from scripts.f4_f5_exit_gate import evaluate

    conn = connect(str(tmp_path / "iic.db"))
    seed_combined_flow(conn)

    report = evaluate(
        conn,
        since=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        window_hours=1,
    )

    assert report["pass"] is True
    assert report["checks"]["light_alert_latency"]["pass"] is True
    assert report["checks"]["alert_quality_audit"]["pass"] is True
    assert report["checks"]["approval_lineage"]["pass"] is True
    assert report["checks"]["full_brief_delivery"]["pass"] is True
    assert report["summaries"]["cost_cache"]["cache_hit_ratio"] == 0.4


def test_combined_gate_fails_without_strict_alert_evaluation(tmp_path):
    from scripts.f4_f5_exit_gate import evaluate

    conn = connect(str(tmp_path / "iic.db"))
    seed_combined_flow(conn)
    conn.execute("DELETE FROM alert_evaluations")
    conn.commit()

    report = evaluate(
        conn,
        since=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        window_hours=1,
    )

    assert report["pass"] is False
    assert report["checks"]["alert_quality_audit"]["pass"] is False
