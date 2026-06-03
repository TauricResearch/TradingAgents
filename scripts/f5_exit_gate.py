"""F5 72-hour soak exit-gate evaluator.

Runs nine checks G1–G9 against the live SQLite store and produces a
markdown artifact at data/exit_gates/f5-<date>.md.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from tradingagents import default_config as _dc
from tradingagents.persistence.db import connect as iic_connect


_F5_UNITS = (
    "iic-telegram-bot.service",
    "iic-action-handler.service",
    "iic-morning.service",
    "iic-dashboard.service",
)


def _g1_morning_digests(conn, since: str) -> tuple[bool, str]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM briefs b
        JOIN deliveries d ON d.brief_id = b.brief_id
        WHERE b.mode = 'morning_digest' AND d.status = 'sent'
          AND b.generated_ts >= ?
        """, (since,),
    ).fetchone()
    n = row["n"]
    return (n >= 3, f"{n} morning_digest deliveries (need >= 3)")


def _g2_event_alerts(conn, since: str) -> tuple[bool, str]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM briefs b
        JOIN deliveries d ON d.brief_id = b.brief_id
        WHERE b.mode IN ('event_alert_light', 'event_alert') AND d.status = 'sent'
          AND b.generated_ts >= ?
        """, (since,),
    ).fetchone()
    return (row["n"] >= 1, f"{row['n']} event_alert/event_alert_light deliveries")


def _g3_deep_dives(conn, since: str) -> tuple[bool, str]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM briefs b
        JOIN deliveries d ON d.brief_id = b.brief_id
        WHERE b.mode = 'deep_dive' AND d.status = 'sent'
          AND b.generated_ts >= ?
        """, (since,),
    ).fetchone()
    return (row["n"] >= 1, f"{row['n']} deep_dive deliveries")


def _g4_backtest_accepted(conn, since: str) -> tuple[bool, str]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM brief_actions
        WHERE action_type = 'run_backtest'
          AND state = 'accepted'
          AND result_backtest_id IS NOT NULL
          AND responded_at >= ?
        """, (since,),
    ).fetchone()
    return (row["n"] >= 1, f"{row['n']} accepted+completed backtests")


def _g5_expired_unactioned(conn, since: str) -> tuple[bool, str]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM brief_actions
        WHERE state = 'expired'
          AND result_backtest_id IS NULL
          AND result_brief_id IS NULL
        """,
    ).fetchone()
    return (row["n"] >= 1, f"{row['n']} expired-with-no-work rows")


def _g6_refinement(conn, since: str) -> tuple[bool, str]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM briefs
        WHERE parent_brief_id IS NOT NULL
          AND refine_overrides IS NOT NULL
          AND generated_ts >= ?
        """, (since,),
    ).fetchone()
    return (row["n"] >= 1, f"{row['n']} refined briefs")


def _check_no_restarts(since: str) -> tuple[bool, str]:
    """Inspect journalctl for Restart=on-failure entries on F5 units."""
    bad = []
    for unit in _F5_UNITS:
        try:
            out = subprocess.check_output(
                ["journalctl", "-u", unit, "--since", since, "--no-pager"],
                stderr=subprocess.STDOUT, timeout=30,
            ).decode("utf-8", errors="replace")
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        if "Restart=on-failure" in out and "failed" in out.lower():
            bad.append(unit)
    return (not bad, f"units with restart events: {bad or 'none'}")


def _g7_no_crashes(since: str) -> tuple[bool, str]:
    return _check_no_restarts(since)


def _g8_cost_data(conn, since: str) -> tuple[bool, str]:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT substr(r.started_ts, 1, 10)) AS days
        FROM costs c JOIN runs r ON r.run_id = c.run_id
        WHERE r.started_ts >= ?
        """, (since,),
    ).fetchone()
    return (row["days"] >= 3, f"{row['days']} days of cost data")


def _g9_guards_off() -> tuple[bool, str]:
    C = _dc.DEFAULT_CONFIG
    keys = [
        ("trigger_backpressure_enabled", C.get("trigger_backpressure_enabled")),
        ("trigger_daily_rate_enabled", C.get("trigger_daily_rate_enabled")),
        ("daily_budget_enabled", C.get("daily_budget_enabled")),
        ("refinement_chain_budget.enabled", C["refinement_chain_budget"]["enabled"]),
        ("morning_digest_token_ceiling.enabled", C["morning_digest_token_ceiling"]["enabled"]),
    ]
    on = [k for k, v in keys if v]
    return (not on, f"guards on: {on or 'none'}")


def evaluate(*, since: str) -> dict:
    conn = iic_connect(_dc.DEFAULT_CONFIG["iic_db_path"])
    checks: dict[str, dict[str, Any]] = {}

    for gid, fn in [
        ("G1", lambda: _g1_morning_digests(conn, since)),
        ("G2", lambda: _g2_event_alerts(conn, since)),
        ("G3", lambda: _g3_deep_dives(conn, since)),
        ("G4", lambda: _g4_backtest_accepted(conn, since)),
        ("G5", lambda: _g5_expired_unactioned(conn, since)),
        ("G6", lambda: _g6_refinement(conn, since)),
        ("G7", lambda: _g7_no_crashes(since)),
        ("G8", lambda: _g8_cost_data(conn, since)),
        ("G9", lambda: _g9_guards_off()),
    ]:
        ok, detail = fn()
        checks[gid] = {"pass": ok, "detail": detail}

    return {
        "since": since,
        "checks": checks,
        "pass": all(c["pass"] for c in checks.values()),
    }


def _write_artifact(report: dict) -> Path:
    out_dir = Path(_dc.DEFAULT_CONFIG["iic_data_dir"]) / "exit_gates"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().date().isoformat()
    path = out_dir / f"f5-{today}.md"
    lines = [
        f"# F5 Exit-Gate Report — {today}",
        f"_since: {report['since']}_",
        "",
        f"**Overall:** {'PASS' if report['pass'] else 'FAIL'}",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for gid, c in report["checks"].items():
        mark = "PASS" if c["pass"] else "FAIL"
        lines.append(f"| {gid} | {mark} | {c['detail']} |")
    path.write_text("\n".join(lines))
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True,
                        help="ISO timestamp marking soak start")
    args = parser.parse_args()
    report = evaluate(since=args.since)
    print(json.dumps(report, indent=2, default=str))
    out = _write_artifact(report)
    print(f"\nReport written to {out}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
