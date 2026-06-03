#!/usr/bin/env python
"""Combined F4/F5 approval-delivery exit-gate evaluator."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.run_recorder import compute_cache_hit_ratio
from tradingagents.persistence.db import connect


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    f, c = int(k), int(k) + 1
    if c >= len(s):
        return s[-1]
    return s[f] + (s[c] - s[f]) * (k - f)


def _seconds(a: str, b: str) -> float:
    aa = datetime.fromisoformat(a.replace("Z", "+00:00"))
    bb = datetime.fromisoformat(b.replace("Z", "+00:00"))
    return (bb - aa).total_seconds()


def _row_count(row: sqlite3.Row | None) -> int:
    return int(row[0] or 0) if row is not None else 0


def _cost_cache_summary(conn: sqlite3.Connection, since: datetime, until: datetime) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
          COUNT(DISTINCT r.run_id) AS runs,
          COALESCE(SUM(c.in_tokens), 0) AS in_tokens,
          COALESCE(SUM(c.out_tokens), 0) AS out_tokens,
          COALESCE(SUM(c.cache_hit_tokens), 0) AS cache_hit_tokens,
          COALESCE(SUM(c.cache_miss_tokens), 0) AS cache_miss_tokens,
          COALESCE(SUM(c.usd_estimate), 0.0) AS usd_estimate
        FROM runs r
        LEFT JOIN costs c ON c.run_id = r.run_id
        WHERE r.started_ts BETWEEN ? AND ?
        """,
        (since.isoformat(), until.isoformat()),
    ).fetchone()
    hit = int(row["cache_hit_tokens"] or 0)
    miss = int(row["cache_miss_tokens"] or 0)
    return {
        "runs": int(row["runs"] or 0),
        "in_tokens": int(row["in_tokens"] or 0),
        "out_tokens": int(row["out_tokens"] or 0),
        "cache_hit_tokens": hit,
        "cache_miss_tokens": miss,
        "cache_hit_ratio": compute_cache_hit_ratio(hit, miss),
        "usd_estimate": float(row["usd_estimate"] or 0.0),
    }


def evaluate(
    conn: sqlite3.Connection,
    *,
    since: datetime,
    window_hours: int,
) -> dict[str, Any]:
    until = since + timedelta(hours=window_hours)
    checks: dict[str, dict[str, Any]] = {}

    light_rows = list(conn.execute(
        """
        SELECT b.brief_id, b.generated_ts, b.trigger_event_id, e.ingested_ts
        FROM briefs b JOIN events e ON e.event_id = b.trigger_event_id
        WHERE b.mode = 'event_alert_light'
          AND b.generated_ts BETWEEN ? AND ?
        """,
        (since.isoformat(), until.isoformat()),
    ))
    latencies = [_seconds(r["ingested_ts"], r["generated_ts"]) for r in light_rows]
    p95 = _percentile(latencies, 0.95) if latencies else 0.0
    checks["light_alert_latency"] = {
        "pass": bool(light_rows) and p95 <= 300,
        "detail": f"{len(light_rows)} light alerts, p95={p95:.1f}s",
    }

    delivered_light = _row_count(conn.execute(
        """
        SELECT COUNT(DISTINCT b.brief_id)
        FROM briefs b JOIN deliveries d ON d.brief_id = b.brief_id
        WHERE b.mode = 'event_alert_light'
          AND d.status IN ('sent', 'skipped')
          AND b.generated_ts BETWEEN ? AND ?
        """,
        (since.isoformat(), until.isoformat()),
    ).fetchone())
    checks["light_delivery_audit"] = {
        "pass": delivered_light >= len(light_rows),
        "detail": (
            f"{delivered_light}/{len(light_rows)} light alerts have "
            "sent/skipped delivery rows"
        ),
    }

    event_count = len({r["trigger_event_id"] for r in light_rows})
    passed_evals = _row_count(conn.execute(
        """
        SELECT COUNT(DISTINCT ae.event_id)
        FROM alert_evaluations ae
        JOIN briefs b ON b.trigger_event_id = ae.event_id
        WHERE b.mode = 'event_alert_light'
          AND b.generated_ts BETWEEN ? AND ?
          AND ae.decision = 'pass'
        """,
        (since.isoformat(), until.isoformat()),
    ).fetchone())
    rejected_evals = _row_count(conn.execute(
        """
        SELECT COUNT(*)
        FROM alert_evaluations ae
        WHERE ae.created_ts BETWEEN ? AND ?
          AND ae.decision != 'pass'
        """,
        (since.isoformat(), until.isoformat()),
    ).fetchone())
    checks["alert_quality_audit"] = {
        "pass": event_count >= 1 and passed_evals >= event_count,
        "detail": (
            f"{passed_evals}/{event_count} light-alert events passed strict "
            f"evaluation; rejects={rejected_evals}"
        ),
    }

    accepted = _row_count(conn.execute(
        """
        SELECT COUNT(*)
        FROM brief_actions
        WHERE action_type = 'run_full_study'
          AND state = 'accepted'
          AND responded_at BETWEEN ? AND ?
        """,
        (since.isoformat(), until.isoformat()),
    ).fetchone())
    lineage = _row_count(conn.execute(
        """
        SELECT COUNT(DISTINCT a.action_id)
        FROM brief_actions a
        JOIN queue_jobs q ON q.job_id = a.result_job_id
        JOIN briefs fb ON fb.brief_id = a.result_brief_id
        WHERE a.action_type = 'run_full_study'
          AND a.state = 'accepted'
          AND q.state = 'done'
          AND fb.mode = 'event_alert'
          AND fb.parent_brief_id = a.brief_id
          AND a.responded_at BETWEEN ? AND ?
        """,
        (since.isoformat(), until.isoformat()),
    ).fetchone())
    checks["approval_lineage"] = {
        "pass": accepted >= 1 and lineage == accepted,
        "detail": (
            f"{lineage}/{accepted} accepted actions completed a done job "
            "and linked full brief"
        ),
    }

    full_delivered = _row_count(conn.execute(
        """
        SELECT COUNT(DISTINCT b.brief_id)
        FROM briefs b JOIN deliveries d ON d.brief_id = b.brief_id
        WHERE b.mode = 'event_alert'
          AND b.parent_brief_id IS NOT NULL
          AND d.status IN ('sent', 'skipped')
          AND b.generated_ts BETWEEN ? AND ?
        """,
        (since.isoformat(), until.isoformat()),
    ).fetchone())
    checks["full_brief_delivery"] = {
        "pass": full_delivered >= lineage,
        "detail": (
            f"{full_delivered}/{lineage} full briefs have sent/skipped "
            "delivery rows"
        ),
    }

    errors = _row_count(conn.execute(
        """
        SELECT COUNT(*)
        FROM queue_jobs
        WHERE state = 'error'
          AND enqueued_ts BETWEEN ? AND ?
        """,
        (since.isoformat(), until.isoformat()),
    ).fetchone())
    checks["worker_errors"] = {
        "pass": errors == 0,
        "detail": f"{errors} queue job errors",
    }

    summaries = {
        "cost_cache": _cost_cache_summary(conn, since, until),
        "operator_signoff": {
            "false_positive_sample_required": True,
            "note": "Operator must sample rejected and passed alert evaluations.",
        },
    }
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "checks": checks,
        "summaries": summaries,
        "pass": all(c["pass"] for c in checks.values()),
    }


def render_md(report: dict[str, Any]) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    lines = [
        f"# F4/F5 Combined Exit-Gate Report - {today}",
        "",
        f"**Window:** `{report['since']}` to `{report['until']}`",
        "",
        f"**Overall:** {'PASS' if report['pass'] else 'FAIL'}",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for name, check in report["checks"].items():
        result = "PASS" if check["pass"] else "FAIL"
        lines.append(f"| {name} | {result} | {check['detail']} |")

    cost = report["summaries"]["cost_cache"]
    ratio = cost["cache_hit_ratio"]
    ratio_text = "n/a" if ratio is None else f"{ratio:.1%}"
    lines += [
        "",
        "## Cost And Cache Summary",
        "",
        f"- runs: {cost['runs']}",
        f"- input/output tokens: {cost['in_tokens']} / {cost['out_tokens']}",
        f"- cache hit/miss tokens: {cost['cache_hit_tokens']} / {cost['cache_miss_tokens']}",
        f"- cache hit ratio: {ratio_text}",
        f"- estimated cost: ${cost['usd_estimate']:.4f}",
        "",
        "## Operator Sign-Off",
        "",
        "- [ ] Review a false-positive/false-negative sample from alert evaluations.",
        "- [ ] Confirm accepted approval lineage maps light alert -> job -> full brief.",
        "- [ ] Confirm full briefs were delivered or explicitly skipped.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True)
    parser.add_argument("--window-hours", type=int, default=12)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    conn = connect(DEFAULT_CONFIG["iic_db_path"])
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    report = evaluate(conn, since=since, window_hours=args.window_hours)
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, default=str))
    else:
        sys.stdout.write(render_md(report))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
