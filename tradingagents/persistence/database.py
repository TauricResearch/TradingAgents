"""Forward-only transactional SQLite migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

Migration = Callable[[sqlite3.Connection], None]


class MigrationError(RuntimeError):
    pass


def _execute_script(conn: sqlite3.Connection, script: str) -> None:
    """Execute our fixed DDL without sqlite3.executescript's implicit commit."""
    for statement in script.split(";"):
        if statement.strip():
            conn.execute(statement)


def _v1(conn: sqlite3.Connection) -> None:
    _execute_script(
        conn,
        """
        CREATE TABLE analysis_jobs (
            id TEXT PRIMARY KEY,
            request_json TEXT NOT NULL,
            status TEXT NOT NULL,
            run_signature TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            error_json TEXT,
            result_json TEXT,
            report_id TEXT,
            advice_id TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            resumable INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE job_events (
            job_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
            event_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            data_json TEXT NOT NULL,
            PRIMARY KEY (job_id, event_id)
        );
        CREATE TABLE reports (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL UNIQUE REFERENCES analysis_jobs(id),
            created_at TEXT NOT NULL,
            result_json TEXT NOT NULL,
            markdown TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE advice_versions (
            id TEXT PRIMARY KEY,
            report_id TEXT NOT NULL REFERENCES reports(id),
            parent_id TEXT REFERENCES advice_versions(id),
            version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            action TEXT NOT NULL,
            confidence TEXT NOT NULL,
            reason TEXT NOT NULL,
            eligibility TEXT NOT NULL,
            trust_assessment_id TEXT,
            trigger_message_ids_json TEXT NOT NULL DEFAULT '[]',
            data_snapshot_json TEXT NOT NULL DEFAULT '{}',
            model_config_json TEXT NOT NULL DEFAULT '{}',
            usage_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE (report_id, version)
        );
        """
    )


def _v2(conn: sqlite3.Connection) -> None:
    _execute_script(
        conn,
        """
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            report_id TEXT NOT NULL REFERENCES reports(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE usage_records (
            id TEXT PRIMARY KEY,
            job_id TEXT REFERENCES analysis_jobs(id),
            conversation_id TEXT REFERENCES conversations(id),
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            requests INTEGER NOT NULL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            retries INTEGER NOT NULL,
            latency_ms INTEGER NOT NULL,
            status TEXT NOT NULL,
            warning TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE conversation_messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_references_json TEXT NOT NULL DEFAULT '[]',
            refreshed_data INTEGER NOT NULL DEFAULT 0,
            candidate_adjustment INTEGER NOT NULL DEFAULT 0,
            usage_record_id TEXT REFERENCES usage_records(id)
        );
        CREATE TABLE source_observations (
            id TEXT PRIMARY KEY,
            job_id TEXT REFERENCES analysis_jobs(id),
            conversation_id TEXT REFERENCES conversations(id),
            source TEXT NOT NULL,
            source_reference TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            published_at TEXT,
            effective_at TEXT,
            raw_hash TEXT NOT NULL,
            cache_status TEXT NOT NULL,
            cache_read_at TEXT
        );
        CREATE TABLE trust_assessments (
            id TEXT PRIMARY KEY,
            job_id TEXT REFERENCES analysis_jobs(id),
            conversation_id TEXT REFERENCES conversations(id),
            level TEXT NOT NULL,
            executable INTEGER NOT NULL,
            reason_codes_json TEXT NOT NULL,
            warnings_json TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            assessed_at TEXT NOT NULL
        );
        """
    )


def _v3(conn: sqlite3.Connection) -> None:
    _execute_script(
        conn,
        """
        CREATE INDEX idx_analysis_jobs_created ON analysis_jobs(created_at DESC);
        CREATE INDEX idx_analysis_jobs_status ON analysis_jobs(status);
        CREATE INDEX idx_events_job_event ON job_events(job_id, event_id);
        CREATE INDEX idx_usage_job_created ON usage_records(job_id, created_at);
        CREATE INDEX idx_usage_day ON usage_records(created_at, provider);
        CREATE INDEX idx_observations_job ON source_observations(job_id, retrieved_at);
        CREATE INDEX idx_trust_job ON trust_assessments(job_id, assessed_at);
        CREATE INDEX idx_messages_conversation ON conversation_messages(conversation_id, created_at);
        """
    )


def _v4(conn: sqlite3.Connection) -> None:
    _execute_script(
        conn,
        """
        ALTER TABLE analysis_jobs ADD COLUMN retry_of_job_id TEXT;
        ALTER TABLE analysis_jobs ADD COLUMN retry_attempt INTEGER NOT NULL DEFAULT 0;
        CREATE INDEX idx_analysis_jobs_retry_of ON analysis_jobs(retry_of_job_id, created_at);
        CREATE TABLE provider_cache (
            provider TEXT NOT NULL,
            symbol TEXT NOT NULL,
            capability TEXT NOT NULL,
            request_params_hash TEXT NOT NULL,
            normalized_json TEXT NOT NULL,
            source_reference TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            effective_at TEXT,
            expires_at TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            PRIMARY KEY (provider, symbol, capability, request_params_hash)
        );
        CREATE INDEX idx_provider_cache_lookup
            ON provider_cache(provider, symbol, capability, request_params_hash);
        CREATE INDEX idx_provider_cache_expiry ON provider_cache(expires_at);
        """,
    )


MIGRATIONS: tuple[tuple[int, Migration], ...] = ((1, _v1), (2, _v2), (3, _v3), (4, _v4))
CURRENT_SCHEMA_VERSION = MIGRATIONS[-1][0]


class Database:
    def __init__(self, path: str | Path, *, migrations: tuple[tuple[int, Migration], ...] = MIGRATIONS):
        self.path = Path(path).expanduser()
        self.migrations = migrations

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def migrate(self) -> int:
        with self.connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
            known = {version for version, _ in self.migrations}
            if applied - known:
                raise MigrationError(f"Database schema is newer than this application: {max(applied - known)}")
            for version, migration in self.migrations:
                if version in applied:
                    continue
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    migration(conn)
                    conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
                    conn.execute("COMMIT")
                except Exception as exc:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise MigrationError(f"Migration {version} failed") from exc
            return self.schema_version(conn)

    @staticmethod
    def schema_version(conn: sqlite3.Connection) -> int:
        try:
            row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
        except sqlite3.DatabaseError:
            return 0
        return int(row[0]) if row else 0
