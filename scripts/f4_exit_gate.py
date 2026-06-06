#!/usr/bin/env python
"""F4 exit-gate evaluator.

Reads queue_jobs / briefs / events over a window and renders the artifact
markdown to stdout. The operator commits the artifact under
docs/superpowers/artifacts/.

Usage:
    python scripts/f4_exit_gate.py --since 2026-05-27T08:00:00Z [--window-hours 12]

For the approval-through-delivery gate that spans F4 and F5, use:
    python scripts/f4_f5_exit_gate.py --since 2026-06-03T09:00:00Z --window-hours 12
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.persistence.db import connect


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    f, c = int(k), int(k) + 1
    if c >= len(s):
        return s[-1]
    return s[f] + (s[c] - s[f]) * (k - f)


def _latency_seconds(ev_ts: str, brief_ts: str) -> float:
    a = datetime.fromisoformat(ev_ts.replace("Z", "+00:00"))
    b = datetime.fromisoformat(brief_ts.replace("Z", "+00:00"))
    return (b - a).total_seconds()


def _systemctl_nrestarts(unit: str) -> int:
    try:
        out = subprocess.check_output(
            ["systemctl", "show", unit, "--property=NRestarts"],
            text=True, stderr=subprocess.DEVNULL,
        )
        return int(out.strip().split("=")[1])
    except Exception:
        return -1   # unknown (not on this host, etc.)


def evaluate(
    conn: sqlite3.Connection, *, since: datetime, window_hours: int = 12,
) -> Dict[str, Any]:
    until = since + timedelta(hours=window_hours)

    rows = list(conn.execute(
        "SELECT b.brief_id, b.generated_ts, b.trigger_event_id, b.scope, "
        "       e.ingested_ts "
        "FROM briefs b JOIN events e ON e.event_id = b.trigger_event_id "
        "WHERE b.mode = 'event_alert_light' "
        "  AND b.generated_ts BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ))

    latencies = [_latency_seconds(r["ingested_ts"], r["generated_ts"]) for r in rows]
    n = len(latencies)
    SLA_S = 5 * 60
    if n >= 3:
        metric = _percentile(latencies, 0.95); rule = "p95"
        sla_pass = metric <= SLA_S
    elif n >= 1:
        metric = max(latencies); rule = "max"
        sla_pass = metric <= SLA_S
    else:
        metric = 0.0; rule = "none"; sla_pass = None

    # Approval plumbing: at least one light alert produced a full brief.
    approved = conn.execute(
        "SELECT COUNT(*) FROM briefs WHERE mode='event_alert' "
        "AND parent_brief_id IS NOT NULL "
        "AND generated_ts BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ).fetchone()[0]

    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "alert_count": n,
        "alert_latency_p50_s": _percentile(latencies, 0.50) if n else 0.0,
        "alert_latency_p95_s": _percentile(latencies, 0.95) if n else 0.0,
        "sla_pass": sla_pass,
        "sla_rule_applied": rule,
        "approved_full_briefs": approved,
        "promoter_nrestarts": _systemctl_nrestarts("iic-promoter"),
        "worker_nrestarts": _systemctl_nrestarts("iic-worker"),
    }


def render_md(result: Dict[str, Any]) -> str:
    out: List[str] = []
    today = datetime.now(timezone.utc).date().isoformat()
    out.append(f"# F4 exit-gate report (approval gate) — {today}")
    out.append("")
    out.append(f"**Window:** `{result['since']}` → `{result['until']}`")
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append(f"- light alerts produced: **{result['alert_count']}**")
    out.append(f"- alert latency p50 / p95: "
               f"{result['alert_latency_p50_s']/60:.2f} / "
               f"{result['alert_latency_p95_s']/60:.2f} min")
    out.append(f"- approved full briefs: **{result['approved_full_briefs']}**")
    out.append("")
    out.append("## Restart audit")
    out.append("")
    out.append(f"- iic-promoter NRestarts: `{result['promoter_nrestarts']}` (must be 0)")
    out.append(f"- iic-worker NRestarts:   `{result['worker_nrestarts']}` (must be 0)")
    out.append("")
    out.append("## SLA verdict (alert latency ≤ 5 min)")
    out.append("")
    sla = result["sla_pass"]; rule = result["sla_rule_applied"]
    if sla is None:
        out.append("- **inconclusive** — 0 light alerts landed in window.")
    elif sla:
        out.append(f"- **PASS** (rule: {rule}, ≤ 5 min)")
    else:
        out.append(f"- **FAIL** (rule: {rule}, > 5 min)")
    out.append("")
    out.append("## Operator sign-off")
    out.append("")
    out.append("- [ ] Operator confirms restart audit, alert-latency SLA, and "
               "that ≥1 approved study produced a full brief.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True,
                    help="ISO-8601 start of the gate window, e.g. 2026-05-27T08:00:00Z")
    ap.add_argument("--window-hours", type=int, default=12)
    args = ap.parse_args()

    db_path = os.environ.get("TRADINGAGENTS_IIC_DB_PATH") or DEFAULT_CONFIG["iic_db_path"]
    conn = connect(db_path)
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    result = evaluate(conn, since=since, window_hours=args.window_hours)
    sys.stdout.write(render_md(result))


if __name__ == "__main__":
    main()
