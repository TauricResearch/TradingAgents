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


@dataclass(frozen=True)
class LogEntryRow:
    """Immutable representation of one log entry."""

    id: int
    analysis_id: int
    timestamp: str
    entry_type: str  # System | Agent | Tool | Data | Error | Control
    content: str


@dataclass(frozen=True)
class RecommendationRow:
    """Immutable representation of a recommendation extracted from an analysis."""

    id: int
    analysis_id: int
    ticker: str
    verdict: str  # BUY|HOLD|SELL|UNDERWEIGHT|OVERWEIGHT|UNKNOWN
    confidence: int | None
    price_at_analysis: float | None
    stop_loss: float | None
    entry_trigger: float | None
    profit_target: float | None
    review_date: str | None
    is_active: int  # 1=active, 0=inactive
    created_at: str
    deactivated_at: str | None
    notes: str | None


@dataclass(frozen=True)
class RecommendationOutcomeRow:
    """Immutable representation of a recommendation outcome check."""

    id: int
    recommendation_id: int
    check_date: str
    days_elapsed: int
    price_at_check: float
    return_pct: float
    stop_hit: int
    target_hit: int
    high_since: float | None
    low_since: float | None


@dataclass(frozen=True)
class AlertRow:
    """Immutable representation of a price alert."""

    id: int
    recommendation_id: int
    ticker: str
    alert_type: str  # stop_loss|entry_trigger|profit_target|custom
    target_price: float
    direction: str  # above|below
    triggered_at: str | None
    triggered_price: float | None
    is_active: int
    created_at: str


@dataclass(frozen=True)
class AlertHistoryRow:
    """Immutable representation of a fired alert event."""

    id: int
    alert_id: int
    fired_at: str
    price: float
    message: str
    seen: int


@dataclass(frozen=True)
class ScheduleRow:
    """Immutable representation of a recurring analysis schedule."""

    id: int
    name: str
    watchlist: str
    cron_expr: str
    timezone: str
    is_enabled: int
    last_run: str | None
    next_run: str | None
    created_at: str


@dataclass(frozen=True)
class ScheduleRunRow:
    """Immutable representation of a single schedule execution."""

    id: int
    schedule_id: int
    started_at: str
    completed_at: str | None
    status: str  # running|completed|failed|skipped_conflict
    tickers_json: str
    results_json: str | None


@dataclass(frozen=True)
class PositionRow:
    """Immutable representation of a portfolio position."""

    id: int
    ticker: str
    quantity: float
    avg_price: float
    date_opened: str | None
    notes: str | None
    updated_at: str


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

                CREATE TABLE IF NOT EXISTS log_entries (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id  INTEGER NOT NULL,
                    timestamp    TEXT    NOT NULL,
                    entry_type   TEXT    NOT NULL,
                    content      TEXT    NOT NULL,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id)
                );

                CREATE INDEX IF NOT EXISTS idx_log_entries_analysis
                    ON log_entries(analysis_id);

                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recommendations (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id       INTEGER NOT NULL REFERENCES analyses(id),
                    ticker            TEXT    NOT NULL,
                    verdict           TEXT    NOT NULL,
                    confidence        INTEGER,
                    price_at_analysis REAL,
                    stop_loss         REAL,
                    entry_trigger     REAL,
                    profit_target     REAL,
                    review_date       TEXT,
                    is_active         INTEGER NOT NULL DEFAULT 1,
                    created_at        TEXT    NOT NULL,
                    deactivated_at    TEXT,
                    notes             TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_recommendations_active
                    ON recommendations(is_active, ticker);
                CREATE INDEX IF NOT EXISTS idx_recommendations_analysis
                    ON recommendations(analysis_id);

                CREATE TABLE IF NOT EXISTS recommendation_outcomes (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    recommendation_id INTEGER NOT NULL REFERENCES recommendations(id),
                    check_date        TEXT    NOT NULL,
                    days_elapsed      INTEGER NOT NULL,
                    price_at_check    REAL    NOT NULL,
                    return_pct        REAL    NOT NULL,
                    stop_hit          INTEGER NOT NULL DEFAULT 0,
                    target_hit        INTEGER NOT NULL DEFAULT 0,
                    high_since        REAL,
                    low_since         REAL,
                    UNIQUE(recommendation_id, days_elapsed)
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    recommendation_id INTEGER NOT NULL REFERENCES recommendations(id),
                    ticker            TEXT    NOT NULL,
                    alert_type        TEXT    NOT NULL,
                    target_price      REAL    NOT NULL,
                    direction         TEXT    NOT NULL,
                    triggered_at      TEXT,
                    triggered_price   REAL,
                    is_active         INTEGER NOT NULL DEFAULT 1,
                    created_at        TEXT    NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_alerts_active
                    ON alerts(is_active, ticker);

                CREATE TABLE IF NOT EXISTS alert_history (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id INTEGER NOT NULL REFERENCES alerts(id),
                    fired_at TEXT    NOT NULL,
                    price    REAL    NOT NULL,
                    message  TEXT    NOT NULL,
                    seen     INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS schedules (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT    NOT NULL,
                    watchlist  TEXT    NOT NULL,
                    cron_expr  TEXT    NOT NULL,
                    timezone   TEXT    NOT NULL DEFAULT 'America/New_York',
                    is_enabled INTEGER NOT NULL DEFAULT 1,
                    last_run   TEXT,
                    next_run   TEXT,
                    created_at TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS schedule_runs (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    schedule_id  INTEGER NOT NULL REFERENCES schedules(id),
                    started_at   TEXT    NOT NULL,
                    completed_at TEXT,
                    status       TEXT    NOT NULL DEFAULT 'running',
                    tickers_json TEXT    NOT NULL,
                    results_json TEXT
                );

                CREATE TABLE IF NOT EXISTS positions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker      TEXT    NOT NULL UNIQUE,
                    quantity    REAL    NOT NULL,
                    avg_price   REAL    NOT NULL,
                    date_opened TEXT,
                    notes       TEXT,
                    updated_at  TEXT    NOT NULL
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
            # WR-04: validate instead of type: ignore
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError("INSERT did not return a row ID")
            return row_id
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
            # WR-06: prefix match so "SP" finds "SPY", "SPXL", etc.
            conditions.append("ticker LIKE ?")
            params.append(ticker.upper() + "%")
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
            # WR-06: prefix match consistent with list_analyses
            conditions.append("ticker LIKE ?")
            params.append(ticker.upper() + "%")
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

    def import_completed_analysis(
        self,
        *,
        ticker: str,
        date: str,
        provider: str,
        model: str,
        result_dir: str,
        selected_analysts: list[str] | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> int:
        """Import a previously completed analysis from disk.

        Used to backfill analyses that ran via CLI before the desktop app
        existed, so they appear in the history table.
        """
        now = datetime.now().isoformat(timespec="seconds")
        analysts_csv = ",".join(selected_analysts or [])
        conn = self._connect()
        try:
            # SEC-01: validate result_dir using is_relative_to
            from desktop.utils.paths import validated_result_dir as _validate

            if _validate(result_dir) is None:
                from pathlib import Path as _Path
                expected_base = (_Path.home() / ".tradingagents" / "results").resolve()
                raise ValueError(f"result_dir must be under {expected_base}")

            cursor = conn.execute(
                """
                INSERT INTO analyses
                    (ticker, date, provider, model, status, started_at,
                     completed_at, config_json, result_dir, selected_analysts)
                VALUES (?, ?, ?, ?, 'completed', ?, ?, '{}', ?, ?)
                """,
                (
                    ticker, date, provider, model,
                    started_at or now, completed_at or now,
                    result_dir, analysts_csv,
                ),
            )
            conn.commit()
            # WR-04: validate instead of type: ignore
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError("INSERT did not return a row ID")
            return row_id
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

    # ── Log entries CRUD ──────────────────────────────────────────────

    def flush_logs(
        self,
        analysis_id: int,
        messages: list[tuple[str, str, str]],
        tool_calls: list[tuple[str, str, Any]],
    ) -> int:
        """Batch-insert log entries from a ProgressSnapshot.

        Called once when an analysis finishes (completed / failed / cancelled).
        Returns the number of rows inserted.
        """
        rows: list[tuple[int, str, str, str]] = []
        for ts, msg_type, content in messages:
            rows.append((analysis_id, ts, msg_type, str(content)))
        for ts, tool_name, args in tool_calls:
            args_str = str(args)
            if len(args_str) > 500:
                args_str = args_str[:497] + "..."
            rows.append((analysis_id, ts, "Tool", f"{tool_name}: {args_str}"))

        if not rows:
            return 0

        conn = self._connect()
        try:
            conn.executemany(
                "INSERT INTO log_entries (analysis_id, timestamp, entry_type, content) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.commit()
            return len(rows)
        finally:
            conn.close()

    def get_log_entries(
        self,
        analysis_id: int,
        *,
        entry_type: str | None = None,
        limit: int = 5000,
    ) -> list[LogEntryRow]:
        """Fetch persisted log entries for an analysis, chronologically."""
        conditions = ["analysis_id = ?"]
        params: list[Any] = [analysis_id]

        if entry_type:
            conditions.append("entry_type = ?")
            params.append(entry_type)

        where = " AND ".join(conditions)
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM log_entries WHERE {where} "
                f"ORDER BY timestamp ASC LIMIT ?",
                [*params, limit],
            ).fetchall()
            return [
                LogEntryRow(
                    id=r["id"],
                    analysis_id=r["analysis_id"],
                    timestamp=r["timestamp"],
                    entry_type=r["entry_type"],
                    content=r["content"],
                )
                for r in rows
            ]
        finally:
            conn.close()

    def count_log_entries(self, analysis_id: int) -> int:
        """Count log entries for an analysis."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM log_entries WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()
            return row[0]
        finally:
            conn.close()

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

    # ── Watchlists (stored in settings as watchlist:{name}) ──────────

    _WATCHLIST_PREFIX = "watchlist:"

    def list_watchlists(self) -> dict[str, list[str]]:
        """Return all saved watchlists as {name: [tickers]}."""
        all_settings = self.get_all_settings()
        result: dict[str, list[str]] = {}
        for key, value in all_settings.items():
            if key.startswith(self._WATCHLIST_PREFIX):
                name = key[len(self._WATCHLIST_PREFIX):]
                tickers = [t.strip().upper() for t in value.split(",") if t.strip()]
                result[name] = tickers
        return result

    def save_watchlist(self, name: str, tickers: list[str]) -> None:
        """Save a named watchlist (overwrites if exists).

        Raises ``ValueError`` if the name is invalid (CR-03 fix).
        """
        name = name.strip()
        if not name or len(name) > 100:
            raise ValueError("Watchlist name must be 1-100 characters")
        if any(c in name for c in (":", "\n", "\r", "\0")):
            raise ValueError("Watchlist name contains invalid characters")
        key = f"{self._WATCHLIST_PREFIX}{name}"
        value = ",".join(t.strip().upper() for t in tickers if t.strip())
        self.set_setting(key, value)

    def delete_watchlist(self, name: str) -> None:
        """Remove a saved watchlist."""
        self.delete_setting(f"{self._WATCHLIST_PREFIX}{name}")

    # ── Recommendations CRUD ───────────────────────────────────────────

    def insert_recommendation(
        self,
        *,
        analysis_id: int,
        ticker: str,
        verdict: str,
        confidence: int | None = None,
        price_at_analysis: float | None = None,
        stop_loss: float | None = None,
        entry_trigger: float | None = None,
        profit_target: float | None = None,
        review_date: str | None = None,
        notes: str | None = None,
    ) -> int:
        """Insert a new recommendation. Returns the row id."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO recommendations
                    (analysis_id, ticker, verdict, confidence,
                     price_at_analysis, stop_loss, entry_trigger,
                     profit_target, review_date, is_active, created_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    analysis_id, ticker.upper(), verdict.upper(), confidence,
                    price_at_analysis, stop_loss, entry_trigger,
                    profit_target, review_date, now, notes,
                ),
            )
            conn.commit()
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError("INSERT did not return a row ID")
            return row_id
        finally:
            conn.close()

    def get_recommendation(self, rec_id: int) -> RecommendationRow | None:
        """Fetch a single recommendation by ID, or None if not found."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM recommendations WHERE id=?", (rec_id,)
            ).fetchone()
            return self._row_to_recommendation(row) if row else None
        finally:
            conn.close()

    def get_recommendation_by_analysis(
        self, analysis_id: int
    ) -> RecommendationRow | None:
        """Fetch the recommendation for a given analysis, or None."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM recommendations WHERE analysis_id=? "
                "ORDER BY id DESC LIMIT 1",
                (analysis_id,),
            ).fetchone()
            return self._row_to_recommendation(row) if row else None
        finally:
            conn.close()

    def list_active_recommendations(self) -> list[RecommendationRow]:
        """Return all active recommendations, newest first."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM recommendations WHERE is_active=1 "
                "ORDER BY id DESC"
            ).fetchall()
            return [self._row_to_recommendation(r) for r in rows]
        finally:
            conn.close()

    def deactivate_recommendation(self, rec_id: int) -> None:
        """Mark a recommendation as inactive."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE recommendations SET is_active=0, deactivated_at=? "
                "WHERE id=?",
                (now, rec_id),
            )
            conn.commit()
        finally:
            conn.close()

    def deactivate_older_for_ticker(self, ticker: str, keep_id: int) -> int:
        """Deactivate all active recommendations for a ticker except *keep_id*.

        Returns the number of rows deactivated.
        """
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE recommendations SET is_active=0, deactivated_at=? "
                "WHERE ticker=? AND is_active=1 AND id!=?",
                (now, ticker.upper(), keep_id),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def _row_to_recommendation(row: sqlite3.Row) -> RecommendationRow:
        return RecommendationRow(
            id=row["id"],
            analysis_id=row["analysis_id"],
            ticker=row["ticker"],
            verdict=row["verdict"],
            confidence=row["confidence"],
            price_at_analysis=row["price_at_analysis"],
            stop_loss=row["stop_loss"],
            entry_trigger=row["entry_trigger"],
            profit_target=row["profit_target"],
            review_date=row["review_date"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            deactivated_at=row["deactivated_at"],
            notes=row["notes"],
        )

    # ── Recommendation Outcomes CRUD ───────────────────────────────────

    def insert_outcome(
        self,
        *,
        recommendation_id: int,
        days_elapsed: int,
        price_at_check: float,
        return_pct: float,
        stop_hit: bool = False,
        target_hit: bool = False,
        high_since: float | None = None,
        low_since: float | None = None,
    ) -> int:
        """Insert a recommendation outcome check. Returns the row id."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO recommendation_outcomes
                    (recommendation_id, check_date, days_elapsed,
                     price_at_check, return_pct, stop_hit, target_hit,
                     high_since, low_since)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recommendation_id, now, days_elapsed,
                    price_at_check, return_pct,
                    int(stop_hit), int(target_hit),
                    high_since, low_since,
                ),
            )
            conn.commit()
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError("INSERT did not return a row ID")
            return row_id
        finally:
            conn.close()

    def get_outcomes(
        self, recommendation_id: int
    ) -> list[RecommendationOutcomeRow]:
        """Fetch all outcome checks for a recommendation, by days ascending."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM recommendation_outcomes "
                "WHERE recommendation_id=? ORDER BY days_elapsed ASC",
                (recommendation_id,),
            ).fetchall()
            return [self._row_to_outcome(r) for r in rows]
        finally:
            conn.close()

    def list_all_outcomes(
        self, *, min_days: int = 0
    ) -> list[RecommendationOutcomeRow]:
        """Fetch all outcomes with at least *min_days* elapsed."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM recommendation_outcomes "
                "WHERE days_elapsed >= ? ORDER BY check_date DESC",
                (min_days,),
            ).fetchall()
            return [self._row_to_outcome(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _row_to_outcome(row: sqlite3.Row) -> RecommendationOutcomeRow:
        return RecommendationOutcomeRow(
            id=row["id"],
            recommendation_id=row["recommendation_id"],
            check_date=row["check_date"],
            days_elapsed=row["days_elapsed"],
            price_at_check=row["price_at_check"],
            return_pct=row["return_pct"],
            stop_hit=row["stop_hit"],
            target_hit=row["target_hit"],
            high_since=row["high_since"],
            low_since=row["low_since"],
        )

    # ── Alerts CRUD ────────────────────────────────────────────────────

    def insert_alert(
        self,
        *,
        recommendation_id: int,
        ticker: str,
        alert_type: str,
        target_price: float,
        direction: str,
    ) -> int:
        """Insert a new price alert. Returns the row id."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO alerts
                    (recommendation_id, ticker, alert_type, target_price,
                     direction, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (recommendation_id, ticker.upper(), alert_type,
                 target_price, direction, now),
            )
            conn.commit()
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError("INSERT did not return a row ID")
            return row_id
        finally:
            conn.close()

    def list_active_alerts(self) -> list[AlertRow]:
        """Return all active (untriggered) alerts."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE is_active=1 ORDER BY ticker, alert_type"
            ).fetchall()
            return [self._row_to_alert(r) for r in rows]
        finally:
            conn.close()

    def trigger_alert(self, alert_id: int, price: float) -> None:
        """Mark an alert as triggered and deactivate it."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE alerts SET triggered_at=?, triggered_price=?, "
                "is_active=0 WHERE id=?",
                (now, price, alert_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row_to_alert(row: sqlite3.Row) -> AlertRow:
        return AlertRow(
            id=row["id"],
            recommendation_id=row["recommendation_id"],
            ticker=row["ticker"],
            alert_type=row["alert_type"],
            target_price=row["target_price"],
            direction=row["direction"],
            triggered_at=row["triggered_at"],
            triggered_price=row["triggered_price"],
            is_active=row["is_active"],
            created_at=row["created_at"],
        )

    # ── Alert History CRUD ─────────────────────────────────────────────

    def insert_alert_history(
        self, *, alert_id: int, price: float, message: str
    ) -> int:
        """Record a fired alert event. Returns the row id."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO alert_history (alert_id, fired_at, price, message, seen) "
                "VALUES (?, ?, ?, ?, 0)",
                (alert_id, now, price, message),
            )
            conn.commit()
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError("INSERT did not return a row ID")
            return row_id
        finally:
            conn.close()

    def list_unseen_alert_history(
        self, limit: int = 50
    ) -> list[AlertHistoryRow]:
        """Return unseen alert history entries, newest first."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM alert_history WHERE seen=0 "
                "ORDER BY fired_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_alert_history(r) for r in rows]
        finally:
            conn.close()

    def mark_alerts_seen(self, alert_ids: list[int]) -> None:
        """Mark alert history entries as seen."""
        if not alert_ids:
            return
        placeholders = ",".join("?" for _ in alert_ids)
        conn = self._connect()
        try:
            conn.execute(
                f"UPDATE alert_history SET seen=1 WHERE id IN ({placeholders})",
                alert_ids,
            )
            conn.commit()
        finally:
            conn.close()

    def list_all_alert_history(self, limit: int = 100) -> list[AlertHistoryRow]:
        """Return all alert history entries, newest first."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM alert_history ORDER BY fired_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_alert_history(r) for r in rows]
        finally:
            conn.close()

    def count_unseen_alert_history(self) -> int:
        """Count unseen alert history entries."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM alert_history WHERE seen=0"
            ).fetchone()
            return row[0]
        finally:
            conn.close()

    def list_alerts_for_recommendation(
        self, recommendation_id: int
    ) -> list[AlertRow]:
        """Return all alerts (active and triggered) for a recommendation."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE recommendation_id=? "
                "ORDER BY alert_type",
                (recommendation_id,),
            ).fetchall()
            return [self._row_to_alert(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _row_to_alert_history(row: sqlite3.Row) -> AlertHistoryRow:
        return AlertHistoryRow(
            id=row["id"],
            alert_id=row["alert_id"],
            fired_at=row["fired_at"],
            price=row["price"],
            message=row["message"],
            seen=row["seen"],
        )

    # ── Schedules CRUD ─────────────────────────────────────────────────

    def insert_schedule(
        self,
        *,
        name: str,
        watchlist: str,
        cron_expr: str,
        timezone: str = "America/New_York",
    ) -> int:
        """Insert a new recurring analysis schedule. Returns the row id."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO schedules
                    (name, watchlist, cron_expr, timezone, is_enabled, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (name, watchlist, cron_expr, timezone, now),
            )
            conn.commit()
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError("INSERT did not return a row ID")
            return row_id
        finally:
            conn.close()

    def list_schedules(self) -> list[ScheduleRow]:
        """Return all schedules, newest first."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM schedules ORDER BY id DESC"
            ).fetchall()
            return [self._row_to_schedule(r) for r in rows]
        finally:
            conn.close()

    def update_schedule_enabled(
        self, schedule_id: int, is_enabled: bool
    ) -> None:
        """Enable or disable a schedule."""
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE schedules SET is_enabled=? WHERE id=?",
                (int(is_enabled), schedule_id),
            )
            conn.commit()
        finally:
            conn.close()

    def update_schedule_last_run(
        self, schedule_id: int, last_run: str, next_run: str | None
    ) -> None:
        """Update the last/next run timestamps for a schedule."""
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE schedules SET last_run=?, next_run=? WHERE id=?",
                (last_run, next_run, schedule_id),
            )
            conn.commit()
        finally:
            conn.close()

    def delete_schedule(self, schedule_id: int) -> None:
        """Delete a schedule and its run history by ID."""
        conn = self._connect()
        try:
            # Delete child rows first (FK constraint)
            conn.execute(
                "DELETE FROM schedule_runs WHERE schedule_id=?", (schedule_id,)
            )
            conn.execute(
                "DELETE FROM schedules WHERE id=?", (schedule_id,)
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row_to_schedule(row: sqlite3.Row) -> ScheduleRow:
        return ScheduleRow(
            id=row["id"],
            name=row["name"],
            watchlist=row["watchlist"],
            cron_expr=row["cron_expr"],
            timezone=row["timezone"],
            is_enabled=row["is_enabled"],
            last_run=row["last_run"],
            next_run=row["next_run"],
            created_at=row["created_at"],
        )

    # ── Schedule Runs CRUD ─────────────────────────────────────────────

    def insert_schedule_run(
        self, *, schedule_id: int, tickers: list[str]
    ) -> int:
        """Insert a new schedule run record. Returns the row id."""
        now = datetime.now().isoformat(timespec="seconds")
        tickers_json = json.dumps(tickers, ensure_ascii=False)
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO schedule_runs
                    (schedule_id, started_at, status, tickers_json)
                VALUES (?, ?, 'running', ?)
                """,
                (schedule_id, now, tickers_json),
            )
            conn.commit()
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError("INSERT did not return a row ID")
            return row_id
        finally:
            conn.close()

    def update_schedule_run(
        self,
        run_id: int,
        *,
        status: str,
        results: list[dict[str, Any]] | None = None,
    ) -> None:
        """Update a schedule run's status and optional results."""
        now = datetime.now().isoformat(timespec="seconds")
        results_json = (
            json.dumps(results, ensure_ascii=False) if results is not None else None
        )
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE schedule_runs SET status=?, completed_at=?, "
                "results_json=? WHERE id=?",
                (status, now, results_json, run_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_schedule_runs(
        self, schedule_id: int, limit: int = 20
    ) -> list[ScheduleRunRow]:
        """Return recent runs for a schedule, newest first."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM schedule_runs WHERE schedule_id=? "
                "ORDER BY id DESC LIMIT ?",
                (schedule_id, limit),
            ).fetchall()
            return [self._row_to_schedule_run(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _row_to_schedule_run(row: sqlite3.Row) -> ScheduleRunRow:
        return ScheduleRunRow(
            id=row["id"],
            schedule_id=row["schedule_id"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            status=row["status"],
            tickers_json=row["tickers_json"],
            results_json=row["results_json"],
        )

    # ── Positions CRUD ─────────────────────────────────────────────────

    def upsert_position(
        self,
        *,
        ticker: str,
        quantity: float,
        avg_price: float,
        date_opened: str | None = None,
        notes: str | None = None,
    ) -> int:
        """Insert or update a portfolio position. Returns the row id."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO positions
                    (ticker, quantity, avg_price, date_opened, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    quantity=excluded.quantity,
                    avg_price=excluded.avg_price,
                    date_opened=excluded.date_opened,
                    notes=excluded.notes,
                    updated_at=excluded.updated_at
                """,
                (ticker.upper(), quantity, avg_price, date_opened, notes, now),
            )
            conn.commit()
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError("INSERT did not return a row ID")
            return row_id
        finally:
            conn.close()

    def list_positions(self) -> list[PositionRow]:
        """Return all portfolio positions, alphabetically by ticker."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM positions ORDER BY ticker ASC"
            ).fetchall()
            return [self._row_to_position(r) for r in rows]
        finally:
            conn.close()

    def delete_position(self, ticker: str) -> None:
        """Delete a position by ticker."""
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM positions WHERE ticker=?", (ticker.upper(),)
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row_to_position(row: sqlite3.Row) -> PositionRow:
        return PositionRow(
            id=row["id"],
            ticker=row["ticker"],
            quantity=row["quantity"],
            avg_price=row["avg_price"],
            date_opened=row["date_opened"],
            notes=row["notes"],
            updated_at=row["updated_at"],
        )
