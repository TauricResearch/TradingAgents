"""SQLite connection + schema-migration entry point.

Loads sqlite-vec at connect time and registers the vec_index virtual table.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Set

import sqlite_vec

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _split_sql_statements(script: str) -> list[str]:
    """Naive splitter: SQLite has no `;` inside our schema strings or comments
    that would confuse a split. PRAGMAs and CREATE/ALTER each end with `;`."""
    out: list[str] = []
    buf: list[str] = []
    for line in script.splitlines():
        stripped = line.split("--", 1)[0]   # strip line comments before checking
        buf.append(line)
        if ";" in stripped:
            out.append("\n".join(buf))
            buf = []
    if buf:
        out.append("\n".join(buf))
    return out

# Tables we expect schema.sql to create (used by tests; keep in sync with the .sql).
_EXPECTED_TABLES: Set[str] = {
    "runs", "costs", "briefs", "brief_actions", "suppression",
    "memories", "outcome_log",
    "backtests", "backtest_runs",
    "events", "event_ticker", "watchlist",
    "queue_jobs", "deliveries",
    # F3:
    "ingest_cursor", "tickers", "event_fingerprints", "event_embeddings",
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

    # Block (rather than immediately error) for up to 5s when another process
    # holds the write lock. The single iic.db is written by sensing, promoter,
    # worker, and dashboard concurrently; without this, writers crash with
    # "database is locked" on any Python whose build default busy_timeout is 0
    # (the conda build happens to default to 5000ms, but we must not rely on
    # that). Idempotent — setting the same PRAGMA repeatedly is harmless.
    conn.execute("PRAGMA busy_timeout=5000")

    # Load the sqlite-vec extension. Must happen before CREATE VIRTUAL TABLE.
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    # Schema. CREATE TABLE/INDEX IF NOT EXISTS are idempotent; ALTER TABLE
    # ADD COLUMN is NOT — sqlite raises "duplicate column name" on a re-run.
    # We split on `;` and apply each statement, suppressing only that error.
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        script = f.read()
    for stmt in _split_sql_statements(script):
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "duplicate column name" in msg:
                continue   # ALTER TABLE re-run — column already present
            raise

    # vec_index is a virtual table; CREATE VIRTUAL TABLE doesn't support
    # IF NOT EXISTS in older SQLite, so guard manually. We also wrap the
    # CREATE in a try/except because the SELECT→CREATE pair is NOT atomic:
    # when multiple threads call connect() concurrently on the same DB
    # (e.g. F1's deepdive launches three personas in parallel), two threads
    # can both observe the table as missing and race to create it. The
    # loser sees "table vec_index already exists" — which is harmless and
    # exactly what we want either way.
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE name='vec_index'"
    ).fetchone()
    if existing is None:
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE vec_index USING vec0(embedding float[384])"
            )
        except sqlite3.OperationalError as e:
            if "already exists" not in str(e):
                raise

    conn.commit()
    return conn
