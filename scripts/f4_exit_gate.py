#!/usr/bin/env python
"""F4 exit-gate evaluator.

Reads queue_jobs / briefs / events over a window and renders the artifact
markdown to stdout. The operator commits the artifact under
docs/superpowers/artifacts/.

Usage:
    python scripts/f4_exit_gate.py --since 2026-05-27T08:00:00Z [--window-hours 12]
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
        "       e.ingested_ts, q.cost_usd, q.state "
        "FROM briefs b "
        "JOIN events e ON e.event_id = b.trigger_event_id "
        "LEFT JOIN queue_jobs q ON q.brief_id = b.brief_id "
        "WHERE b.mode = 'event_alert' "
        "  AND b.generated_ts BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ))

    per_brief = []
    latencies = []
    total_cost = 0.0
    for r in rows:
        lat = _latency_seconds(r["ingested_ts"], r["generated_ts"])
        latencies.append(lat)
        cost = float(r["cost_usd"] or 0.0)
        total_cost += cost
        per_brief.append({
            "brief_id": r["brief_id"],
            "ticker": r["scope"],
            "event_id": r["trigger_event_id"],
            "ingested_ts": r["ingested_ts"],
            "brief_ts": r["generated_ts"],
            "latency_min": lat / 60.0,
            "cost_usd": cost,
        })

    n = len(per_brief)
    if n >= 3:
        p95 = _percentile(latencies, 0.95)
        sla_pass = p95 <= 15 * 60
        sla_rule = "p95"
    elif n >= 1:
        max_lat = max(latencies)
        sla_pass = max_lat <= 15 * 60
        sla_rule = "max"
    else:
        sla_pass = None
        sla_rule = "none"

    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "brief_count": n,
        "per_brief": per_brief,
        "latencies_s": latencies,
        "latency_p50_s": _percentile(latencies, 0.50) if n else 0.0,
        "latency_p95_s": _percentile(latencies, 0.95) if n else 0.0,
        "latency_p99_s": _percentile(latencies, 0.99) if n else 0.0,
        "total_cost_usd": total_cost,
        "sla_pass": sla_pass,
        "sla_rule_applied": sla_rule,
        "promoter_nrestarts": _systemctl_nrestarts("iic-promoter"),
        "worker_nrestarts": _systemctl_nrestarts("iic-worker"),
    }


def render_md(result: Dict[str, Any]) -> str:
    out: List[str] = []
    today = datetime.now(timezone.utc).date().isoformat()
    out.append(f"# F4 exit-gate report — {today}")
    out.append("")
    out.append(f"**Window:** `{result['since']}` → `{result['until']}`")
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append(f"- briefs produced: **{result['brief_count']}**")
    out.append(f"- total cost: **${result['total_cost_usd']:.4f}**")
    out.append(f"- latency p50 / p95 / p99: "
               f"{result['latency_p50_s']/60:.2f} / "
               f"{result['latency_p95_s']/60:.2f} / "
               f"{result['latency_p99_s']/60:.2f} min")
    out.append("")
    out.append("## Restart audit")
    out.append("")
    out.append(f"- iic-promoter NRestarts: `{result['promoter_nrestarts']}` "
               f"(must be 0; -1 = host check unavailable)")
    out.append(f"- iic-worker NRestarts:   `{result['worker_nrestarts']}` "
               f"(must be 0)")
    out.append("")
    out.append("## Per-brief table")
    out.append("")
    out.append("| brief_id | ticker | event_id | ingested | brief | latency (min) | cost |")
    out.append("|---|---|---|---|---|---|---|")
    for b in result["per_brief"]:
        out.append(
            f"| `{b['brief_id'][:8]}` | {b['ticker']} | `{b['event_id'][:8]}` "
            f"| {b['ingested_ts'][:19]} | {b['brief_ts'][:19]} "
            f"| {b['latency_min']:.2f} | ${b['cost_usd']:.4f} |"
        )
    out.append("")
    out.append("## SLA verdict")
    out.append("")
    sla_pass = result["sla_pass"]
    rule = result["sla_rule_applied"]
    if sla_pass is None:
        out.append("- **inconclusive** — 0 briefs landed in window. Re-run during a more active period.")
    elif sla_pass:
        out.append(f"- **PASS** (rule: {rule}, ≤ 15 min)")
    else:
        out.append(f"- **FAIL** (rule: {rule}, > 15 min)")
    out.append("")
    out.append("## Synthetic-smoke result")
    out.append("")
    out.append("- `tests/smoke/test_f4_exit_gate.py` on commit `<COMMIT>`: __PASS__ / __FAIL__ (fill manually)")
    out.append("")
    out.append("## Operator sign-off")
    out.append("")
    out.append("- [ ] Operator confirms restart audit and SLA verdict above.")
    out.append("- Notes: ____________________________________________________________")
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
