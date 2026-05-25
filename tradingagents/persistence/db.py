"""SQLite connection + schema-migration entry point.

Loads sqlite-vec at connect time and registers the vec_index virtual table.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Set

import sqlite_vec

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Tables we expect schema.sql to create (used by tests; keep in sync with the .sql).
_EXPECTED_TABLES: Set[str] = {
    "runs", "costs", "briefs", "brief_actions", "suppression",
    "memories", "outcome_log",
    "backtests", "backtest_runs",
    "events", "event_ticker", "watchlist",
    "queue_jobs", "deliveries",
}


def schema_tables() -> Set[str]:
    """Tables expected after a fresh ``connect()``."""
    return _EXPECTED_TABLES


def connect(db_path: str) -> sqlite3.Connection:
    """Open a connection, run schema.sql, load sqlite-vec, create vec_index.

    Idempotent: safe to call repeatedly on the same db file.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Load the sqlite-vec extension. Must happen before CREATE VIRTUAL TABLE.
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    # Schema (idempotent because every CREATE uses IF NOT EXISTS).
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    # vec_index is a virtual table; CREATE VIRTUAL TABLE doesn't support
    # IF NOT EXISTS in older SQLite, so guard manually.
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE name='vec_index'"
    ).fetchone()
    if existing is None:
        conn.execute(
            "CREATE VIRTUAL TABLE vec_index USING vec0(embedding float[384])"
        )

    conn.commit()
    return conn
