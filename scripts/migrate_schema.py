#!/usr/bin/env python3
"""
Extend Hermes' SQLite DB with trading-specific tables.
Run once via: python /opt/scripts/migrate_schema.py

Safe to re-run — all statements use CREATE TABLE IF NOT EXISTS.
"""

import os
import sqlite3
import sys


HERMES_DB_PATH = os.environ.get("HERMES_DB_PATH", "/opt/data/hermes.db")

TABLES = [
    (
        "trades",
        """
        CREATE TABLE IF NOT EXISTS trades (
            id              TEXT PRIMARY KEY,
            ticker          TEXT NOT NULL,
            date_open       TEXT NOT NULL,
            date_close      TEXT,
            entry_price     REAL,
            stop_price      REAL,
            target_price    REAL,
            shares          INTEGER,
            signal          TEXT,
            pnl_dollars     REAL,
            pnl_pct         REAL,
            outcome         TEXT,
            regime          TEXT,
            analysts_fired  TEXT,
            scenario        TEXT,
            actual_outcome  TEXT,
            skill_used      TEXT,
            notes           TEXT
        )
        """,
    ),
    (
        "daily_snapshots",
        """
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            date            TEXT PRIMARY KEY,
            account_equity  REAL,
            open_positions  INTEGER,
            realized_pnl    REAL,
            unrealized_pnl  REAL
        )
        """,
    ),
    (
        "analyst_performance",
        """
        CREATE TABLE IF NOT EXISTS analyst_performance (
            analyst_name    TEXT NOT NULL,
            date            TEXT NOT NULL,
            signal_fired    TEXT,
            trade_id        TEXT,
            outcome         TEXT,
            PRIMARY KEY (analyst_name, date, trade_id)
        )
        """,
    ),
]

FTS_TABLE = (
    "trades_fts",
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS trades_fts USING fts5(
        ticker, regime, signal, scenario, analysts_fired, notes,
        content=trades, content_rowid=rowid
    )
    """,
)

# Triggers to keep the FTS5 content table in sync with the trades table.
# Without these, inserting/updating/deleting rows in `trades` directly
# would leave trades_fts stale (FTS5 content tables don't auto-update).
FTS_TRIGGERS = [
    (
        "trades_ai",
        """
        CREATE TRIGGER IF NOT EXISTS trades_ai AFTER INSERT ON trades BEGIN
            INSERT INTO trades_fts(rowid, ticker, regime, signal, scenario, analysts_fired, notes)
            VALUES (new.rowid, new.ticker, new.regime, new.signal, new.scenario, new.analysts_fired, new.notes);
        END
        """,
    ),
    (
        "trades_ad",
        """
        CREATE TRIGGER IF NOT EXISTS trades_ad AFTER DELETE ON trades BEGIN
            INSERT INTO trades_fts(trades_fts, rowid, ticker, regime, signal, scenario, analysts_fired, notes)
            VALUES ('delete', old.rowid, old.ticker, old.regime, old.signal, old.scenario, old.analysts_fired, old.notes);
        END
        """,
    ),
    (
        "trades_au",
        """
        CREATE TRIGGER IF NOT EXISTS trades_au AFTER UPDATE ON trades BEGIN
            INSERT INTO trades_fts(trades_fts, rowid, ticker, regime, signal, scenario, analysts_fired, notes)
            VALUES ('delete', old.rowid, old.ticker, old.regime, old.signal, old.scenario, old.analysts_fired, old.notes);
            INSERT INTO trades_fts(rowid, ticker, regime, signal, scenario, analysts_fired, notes)
            VALUES (new.rowid, new.ticker, new.regime, new.signal, new.scenario, new.analysts_fired, new.notes);
        END
        """,
    ),
]


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'shadow') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def migrate(db_path: str) -> None:
    print(f"DB path: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.OperationalError as exc:
        print(f"ERROR: Cannot open database at {db_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    created = 0
    existed = 0

    with conn:
        for name, ddl in TABLES:
            already = table_exists(conn, name)
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError as exc:
                print(f"ERROR: Failed to create table '{name}': {exc}", file=sys.stderr)
                conn.close()
                sys.exit(1)

            if already:
                print(f"  Already exists: '{name}'")
                existed += 1
            else:
                print(f"  Created: '{name}'")
                created += 1

        # FTS5 virtual table
        fts_name, fts_ddl = FTS_TABLE
        fts_already = table_exists(conn, fts_name)
        fts_ok = False
        try:
            conn.execute(fts_ddl)
            fts_ok = True
        except sqlite3.OperationalError as exc:
            # FTS5 not available in this SQLite build
            print(
                f"WARNING: Could not create FTS5 table '{fts_name}': {exc}",
                file=sys.stderr,
            )
            print(
                "  Full-text search on trades will be unavailable. "
                "Ensure SQLite was compiled with FTS5 support.",
                file=sys.stderr,
            )
        else:
            if fts_already:
                print(f"  Already exists: '{fts_name}' (virtual/FTS5)")
                existed += 1
            else:
                print(f"  Created: '{fts_name}' (virtual/FTS5)")
                created += 1

        # FTS5 sync triggers — keep index in sync with direct inserts/updates/deletes
        if fts_ok:
            for trigger_name, trigger_ddl in FTS_TRIGGERS:
                try:
                    conn.execute(trigger_ddl)
                    # triggers don't appear in sqlite_master by CREATE IF NOT EXISTS result,
                    # so just confirm they exist after execution
                    exists = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='trigger' AND name=?",
                        (trigger_name,),
                    ).fetchone()
                    if exists:
                        print(f"  Trigger ready: '{trigger_name}'")
                    else:
                        print(f"  Created trigger: '{trigger_name}'")
                except sqlite3.OperationalError as exc:
                    print(
                        f"  WARNING: Could not create trigger '{trigger_name}': {exc}",
                        file=sys.stderr,
                    )

    conn.close()
    total = created + existed
    print(
        f"\nMigration complete. {total} tables checked — "
        f"{created} created, {existed} already existed."
    )


if __name__ == "__main__":
    migrate(HERMES_DB_PATH)
