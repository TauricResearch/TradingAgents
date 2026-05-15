"""SQLite database for analysis history and application settings.

Uses WAL mode for safe concurrent reads (UI thread) alongside writes
(pipeline thread). All public methods are short-lived and open/close
their own connections -- no long-lived cursors.

Schema
------
- ``analyses``  -- one row per analysis run (F3)
- ``settings``  -- key/value pairs for user preferences (F5)

See also: PLAN-desktop.md, Phase 2.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Data transfer objects ───────────────────────────────────────────────

@dataclass(frozen=True)
class AnalysisRow:
    """Immutable representation of one analysis run."""

    id: int
    ticker: str
    date: str
    provider: str
    model: str
    status: str  # running | completed | interrupted | failed
    started_at: str
    completed_at: str | None
    config_json: str
    result_dir: str | None
    error_text: str | None
    selected_analysts: str  # comma-separated analyst keys


# ── Default database path ──────────────────────────────────────────────

_DEFAULT_DB_DIR = Path.home() / ".tradingagents"


# ── Database class ─────────────────────────────────────────────────────


class HistoryDB:
    """SQLite database for analysis history and settings.

    Parameters
    ----------
    db_path : Path, optional
        Override the database file location (useful for tests).
        Defaults to ``~/.tradingagents/app.db``.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            _DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
            db_path = _DEFAULT_DB_DIR / "app.db"
        self._db_path = db_path
        self._ensure_schema()

    # ── Connection helper ───────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        """Open a short-lived connection with WAL mode and busy timeout."""
        conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        """Create tables if they don't exist yet."""
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker          TEXT    NOT NULL,
                    date            TEXT    NOT NULL,
                    provider        TEXT    NOT NULL,
                    model           TEXT    NOT NULL,
                    status          TEXT    NOT NULL DEFAULT 'running',
                    started_at      TEXT    NOT NULL,
                    completed_at    TEXT,
                    config_json     TEXT    NOT NULL DEFAULT '{}',
                    result_dir      TEXT,
                    error_text      TEXT,
                    selected_analysts TEXT  NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_analyses_ticker
                    ON analyses(ticker);
                CREATE INDEX IF NOT EXISTS idx_analyses_status
                    ON analyses(status);

                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    # ── Analyses CRUD ───────────────────────────────────────────────

    def insert_analysis(
        self,
        *,
        ticker: str,
        date: str,
        provider: str,
        model: str,
        config: dict[str, Any] | None = None,
        result_dir: str | None = None,
        selected_analysts: list[str] | None = None,
    ) -> int:
        """Insert a new analysis row (status='running'). Returns the row id."""
        now = datetime.now().isoformat(timespec="seconds")
        config_json = json.dumps(config or {}, ensure_ascii=False)
        analysts_csv = ",".join(selected_analysts or [])

        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO analyses
                    (ticker, date, provider, model, status, started_at,
                     config_json, result_dir, selected_analysts)
                VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?)
                """,
                (ticker, date, provider, model, now, config_json, result_dir, analysts_csv),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]
        finally:
            conn.close()

    def mark_completed(self, analysis_id: int) -> None:
        """Mark an analysis as successfully completed."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE analyses SET status='completed', completed_at=? WHERE id=?",
                (now, analysis_id),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_failed(self, analysis_id: int, error_text: str) -> None:
        """Mark an analysis as failed with an error message."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE analyses SET status='failed', completed_at=?, error_text=? WHERE id=?",
                (now, error_text, analysis_id),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_interrupted(self, analysis_id: int) -> None:
        """Mark an analysis as interrupted (app quit / cancel / agent stuck)."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE analyses SET status='interrupted', completed_at=? WHERE id=?",
                (now, analysis_id),
            )
            conn.commit()
        finally:
            conn.close()

    def update_result_dir(self, analysis_id: int, result_dir: str) -> None:
        """Set the result directory path for an analysis."""
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE analyses SET result_dir=? WHERE id=?",
                (result_dir, analysis_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_analysis(self, analysis_id: int) -> AnalysisRow | None:
        """Fetch a single analysis by ID, or None if not found."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM analyses WHERE id=?", (analysis_id,)
            ).fetchone()
            return self._row_to_analysis(row) if row else None
        finally:
            conn.close()

    def list_analyses(
        self,
        *,
        ticker: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AnalysisRow]:
        """List analyses with optional filtering, newest first."""
        conditions: list[str] = []
        params: list[Any] = []

        if ticker:
            conditions.append("ticker = ?")
            params.append(ticker.upper())
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM analyses {where} ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        conn = self._connect()
        try:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_analysis(r) for r in rows]
        finally:
            conn.close()

    def count_analyses(
        self, *, ticker: str | None = None, status: str | None = None
    ) -> int:
        """Count analyses matching optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if ticker:
            conditions.append("ticker = ?")
            params.append(ticker.upper())
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        conn = self._connect()
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM analyses {where}", params).fetchone()
            return row[0]
        finally:
            conn.close()

    @staticmethod
    def _row_to_analysis(row: sqlite3.Row) -> AnalysisRow:
        return AnalysisRow(
            id=row["id"],
            ticker=row["ticker"],
            date=row["date"],
            provider=row["provider"],
            model=row["model"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            config_json=row["config_json"],
            result_dir=row["result_dir"],
            error_text=row["error_text"],
            selected_analysts=row["selected_analysts"],
        )

    # ── Settings CRUD ───────────────────────────────────────────────

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Read a setting value by key."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
            return row["value"] if row else default
        finally:
            conn.close()

    def set_setting(self, key: str, value: str) -> None:
        """Upsert a setting value."""
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()

    def get_all_settings(self) -> dict[str, str]:
        """Return all settings as a dictionary."""
        conn = self._connect()
        try:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            return {r["key"]: r["value"] for r in rows}
        finally:
            conn.close()

    def delete_setting(self, key: str) -> None:
        """Delete a setting by key."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM settings WHERE key=?", (key,))
            conn.commit()
        finally:
            conn.close()
