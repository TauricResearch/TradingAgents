"""Fingerprint the assistant's runtime state — run before and after a machine move.

The failure mode a migration has to rule out is silent: point the app at a
missing database and SQLAlchemy creates an empty one, the dashboard renders,
the scheduler starts, and everything looks healthy while the paper-trading
history is gone. Row counts are the cheapest proof that did NOT happen.

Usage (from the repo root, so relative paths resolve the same way the app
resolves them):

    python scripts/verify_migration.py                 # human-readable
    python scripts/verify_migration.py --json > a.json # machine-readable

Run it on the old PC before unplugging, again on the new PC after restoring,
and diff. Counts should match exactly; only ``generated_at`` differs.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

#: Mirrors ``AssistantSettings.database_url``: ASSISTANT_DB_URL wins, otherwise
#: the app falls back to ~/.tradingagents/assistant.db. Checked in that order so
#: this script reports on the same file the app would actually open.
_FALLBACK = Path.home() / ".tradingagents" / "assistant.db"

#: Tables whose row counts constitute the experiment. Anything missing here is
#: reported rather than skipped — a dropped table is exactly what we're hunting.
_TABLES = (
    "paper_account",
    "positions",
    "trades",
    "signals",
    "equity_snapshots",
    "watchlist",
    "schedule_slots",
    "screener_results",
)


def resolve_db_path() -> Path:
    """Return the SQLite file the app would open, honouring ASSISTANT_DB_URL."""
    url = os.environ.get("ASSISTANT_DB_URL", "").strip()
    if not url:
        # .env is not loaded in a bare `python` process, so read it directly.
        # Decoded as utf-8-sig because PowerShell 5.1 writes a BOM (see CLAUDE.md).
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_bytes().decode("utf-8-sig").splitlines():
                line = line.strip()
                if line.startswith("ASSISTANT_DB_URL=") and not line.startswith("#"):
                    url = line.partition("=")[2].strip().strip('"').strip("'")
                    break
    if not url:
        return _FALLBACK
    # sqlite+aiosqlite:///data/assistant.db -> data/assistant.db (relative)
    # sqlite+aiosqlite:///C:/x/assistant.db -> C:/x/assistant.db (absolute)
    _, _, tail = url.partition(":///")
    return Path(tail or url)


def collect(db_path: Path) -> dict:
    report: dict = {
        "database": str(db_path),
        "exists": db_path.exists(),
        "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
        "tables": {},
        "accounts": [],
        "equity_range": None,
    }
    if not db_path.exists():
        return report

    con = sqlite3.connect(str(db_path))
    try:
        present = {r[0] for r in con.execute(
            "select name from sqlite_master where type='table'")}
        for table in _TABLES:
            if table not in present:
                report["tables"][table] = "MISSING"
                continue
            report["tables"][table] = con.execute(
                f"select count(*) from {table}").fetchone()[0]

        if "paper_account" in present:
            for row in con.execute(
                "select label, starting_cash, cash from paper_account order by id"
            ):
                report["accounts"].append(
                    {"label": row[0], "starting_cash": row[1], "cash": round(row[2], 2)}
                )

        if "equity_snapshots" in present:
            lo, hi = con.execute(
                "select min(snapshot_date), max(snapshot_date) from equity_snapshots"
            ).fetchone()
            report["equity_range"] = [lo, hi]
    finally:
        con.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args()

    report = collect(resolve_db_path())

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["exists"] else 1

    print(f"database : {report['database']}")
    if not report["exists"]:
        print("STATUS   : MISSING — the app would create a fresh, empty database here.")
        return 1
    print(f"size     : {report['size_bytes']:,} bytes")
    print()
    print("row counts")
    for table, count in report["tables"].items():
        print(f"  {table:<20} {count}")
    print()
    print("paper books")
    for acct in report["accounts"]:
        print(
            f"  {acct['label']:<12} start {acct['starting_cash']:>10,.2f}"
            f"   cash {acct['cash']:>10,.2f}"
        )
    if report["equity_range"]:
        lo, hi = report["equity_range"]
        print()
        print(f"equity snapshots span {lo} -> {hi}")

    empty = [t for t, c in report["tables"].items() if c in (0, "MISSING")]
    print()
    if empty:
        print(f"WARNING: empty or missing tables: {', '.join(empty)}")
        return 1
    print("OK — every tracked table has rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
