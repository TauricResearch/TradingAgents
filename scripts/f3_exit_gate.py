"""F3 exit-gate evaluator.

Usage:
    python scripts/f3_exit_gate.py --since "2026-05-26T14:00:00Z"

Writes an artifact under docs/superpowers/artifacts/<date>-f3-exit-gate-report.md
and exits 0 if every *automatic* criterion passed (spot-check is a separate
human sign-off in the artifact). Exits 1 on automatic-criterion failure.
"""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Sequence

from tradingagents.persistence.db import connect


_DEFAULT_SERVICES = [
    "iic-sense-polygon", "iic-sense-telegram", "iic-sense-x",
    "iic-sense-rss", "iic-sense-gdelt", "iic-sense-macro",
    "iic-triage",
]


@dataclass
class ExitGateResult:
    since: datetime
    until: datetime
    events_total: int
    duplicates: int
    active: int
    autos: int
    restarts: Dict[str, int] = field(default_factory=dict)
    spot_sample: List[dict] = field(default_factory=list)
    crit_events: bool = False
    crit_autos: bool = False
    crit_restarts: bool = False
    passed_auto: bool = False


def _check_systemctl_restarts(services: Sequence[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for svc in services:
        try:
            r = subprocess.run(
                ["systemctl", "show", f"{svc}.service",
                 "--property=NRestarts", "--value"],
                check=True, capture_output=True, text=True, timeout=5,
            )
            out[svc] = int((r.stdout or "0").strip() or 0)
        except Exception:
            out[svc] = -1  # unknown — treat as failure
    return out


def evaluate(
    *,
    db_path: str,
    since: datetime,
    services: Sequence[str] | None = None,
    check_systemd: bool = True,
) -> ExitGateResult:
    services = list(services) if services is not None else _DEFAULT_SERVICES
    conn = connect(db_path)
    until = since + timedelta(hours=24)
    events = list(conn.execute(
        "SELECT event_id, source, status, deduped_of, ingested_ts "
        "FROM events WHERE ingested_ts BETWEEN ? AND ?",
        (since.isoformat(), until.isoformat()),
    ))
    duplicates = [e for e in events if e["status"] == "duplicate"]
    active = [e for e in events if e["status"] == "triaged"]
    autos = list(conn.execute(
        "SELECT ticker, added_ts, tags FROM watchlist "
        "WHERE added_ts BETWEEN ? AND ? AND tags LIKE '%\"auto\"%'",
        (since.isoformat(), until.isoformat()),
    ))

    restarts: Dict[str, int] = {}
    if check_systemd:
        restarts = _check_systemctl_restarts(services)
    crit_restarts = (not restarts) or all(n == 0 for n in restarts.values())

    sample = random.sample(duplicates, min(30, len(duplicates))) if duplicates else []
    spot_sample: List[dict] = []
    for d in sample:
        orig = conn.execute(
            "SELECT event_id, source, ingested_ts FROM events WHERE event_id = ?",
            (d["deduped_of"],),
        ).fetchone()
        spot_sample.append({
            "dup": dict(d),
            "orig": dict(orig) if orig else None,
        })

    res = ExitGateResult(
        since=since, until=until,
        events_total=len(events), duplicates=len(duplicates),
        active=len(active), autos=len(autos),
        restarts=restarts, spot_sample=spot_sample,
        crit_events=(len(events) >= 100),
        crit_autos=(len(autos) >= 1),
        crit_restarts=crit_restarts,
    )
    res.passed_auto = res.crit_events and res.crit_autos and res.crit_restarts
    return res


def render_report(r: ExitGateResult) -> str:
    lines = [
        f"# F3 Exit-Gate Report — {r.since.date().isoformat()}",
        "",
        f"Window: `{r.since.isoformat()}` → `{r.until.isoformat()}`",
        "",
        "## Auto-criteria",
        "",
        f"- events ≥ 100: **{r.crit_events}** ({r.events_total} events)",
        f"- auto-promoted watchlist rows ≥ 1: **{r.crit_autos}** ({r.autos})",
        f"- no adapter restarts: **{r.crit_restarts}**",
        "",
        "## Per-adapter NRestarts",
        "",
    ]
    if r.restarts:
        for svc, n in sorted(r.restarts.items()):
            badge = "OK" if n == 0 else ("UNKNOWN" if n < 0 else f"FAIL ({n})")
            lines.append(f"- `{svc}.service`: {badge}")
    else:
        lines.append("(systemd check skipped — running outside the host)")
    lines += [
        "",
        "## Counts",
        "",
        f"- total events: {r.events_total}",
        f"- triaged: {r.active}",
        f"- duplicates: {r.duplicates}",
        f"- duplicates / total: "
        f"{(r.duplicates / r.events_total * 100):.1f}%" if r.events_total else "n/a",
        "",
        "## Dedup spot-check sample (30 rows)",
        "",
    ]
    for i, s in enumerate(r.spot_sample, 1):
        dup = s["dup"]; orig = s["orig"]
        lines.append(f"### sample {i}")
        lines.append(f"- duplicate: `{dup['event_id']}` ({dup['source']}, {dup['ingested_ts']})")
        if orig:
            lines.append(f"- original: `{orig['event_id']}` ({orig['source']}, {orig['ingested_ts']})")
        lines.append("")
    lines += [
        "## Sign-off",
        "",
        "Spot-check pass (≥24/30 are genuine duplicates): **YES / NO** — _reviewer notes here_",
        "",
        f"Overall auto-pass: **{r.passed_auto}**",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--since", required=True,
                   help="UTC ISO-8601 start of the 24h window")
    p.add_argument("--db", default=None,
                   help="Path to iic.db (defaults to DEFAULT_CONFIG)")
    p.add_argument("--no-systemd", action="store_true",
                   help="Skip systemctl restart checks")
    args = p.parse_args(argv)

    from tradingagents.default_config import DEFAULT_CONFIG as C
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    res = evaluate(db_path=args.db or C["iic_db_path"],
                   since=since, check_systemd=not args.no_systemd)
    out_dir = Path("docs/superpowers/artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{since.date().isoformat()}-f3-exit-gate-report.md"
    out_path.write_text(render_report(res))
    print(f"wrote {out_path}")
    print(f"events={res.events_total}  duplicates={res.duplicates}  "
          f"autos={res.autos}  passed_auto={res.passed_auto}")
    return 0 if res.passed_auto else 1


if __name__ == "__main__":
    sys.exit(main())
