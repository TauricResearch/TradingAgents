import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Literal, Optional

from api.models.run import RunConfig, RunResult, RunStatus, TokenUsage

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    ticker      TEXT NOT NULL,
    date        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued',
    decision    TEXT,
    created_at  TEXT NOT NULL,
    config      TEXT,
    reports     TEXT NOT NULL DEFAULT '{}',
    error       TEXT,
    token_usage TEXT NOT NULL DEFAULT '{}'
)
"""


class RunsStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE_SQL)
        # Migration: add token_usage column if not present (handles existing DBs)
        existing_cols = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(runs)")
        }
        if "token_usage" not in existing_cols:
            self._conn.execute(
                "ALTER TABLE runs ADD COLUMN token_usage TEXT NOT NULL DEFAULT '{}'"
            )
        self._conn.commit()
        self._lock = Lock()

    def _row_to_run(self, row: sqlite3.Row) -> RunResult:
        return RunResult(
            id=row["id"],
            ticker=row["ticker"],
            date=row["date"],
            status=RunStatus(row["status"]),
            decision=row["decision"],
            created_at=row["created_at"],
            config=RunConfig(**json.loads(row["config"])) if row["config"] else None,
            reports=json.loads(row["reports"]),
            error=row["error"],
            token_usage={
                k: TokenUsage(**v)
                for k, v in json.loads(row["token_usage"] or "{}").items()
            },
        )

    def create(self, config: RunConfig) -> RunResult:
        run_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs (id, ticker, date, status, created_at, config)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, config.ticker, config.date, RunStatus.QUEUED.value,
                 now, config.model_dump_json()),
            )
            self._conn.commit()
        return RunResult(
            id=run_id,
            ticker=config.ticker,
            date=config.date,
            status=RunStatus.QUEUED,
            created_at=now,
            config=config,
        )

    def get(self, run_id: str) -> Optional[RunResult]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._row_to_run(row) if row else None

    def list_all(self) -> list[RunResult]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def update_status(self, run_id: str, status: RunStatus) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET status = ? WHERE id = ?",
                (status.value, run_id),
            )
            self._conn.commit()

    def update_decision(
        self, run_id: str, decision: Literal["BUY", "SELL", "HOLD"]
    ) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET decision = ? WHERE id = ?",
                (decision, run_id),
            )
            self._conn.commit()

    def add_report(self, run_id: str, step: str, report: str) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT reports FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row:
                reports = json.loads(row[0])
                reports[step] = report
                self._conn.execute(
                    "UPDATE runs SET reports = ? WHERE id = ?",
                    (json.dumps(reports), run_id),
                )
                self._conn.commit()

    def set_error(self, run_id: str, error: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET status = ?, error = ? WHERE id = ?",
                (RunStatus.ERROR.value, error, run_id),
            )
            self._conn.commit()

    def clear_reports(self, run_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET reports = '{}' WHERE id = ?",
                (run_id,),
            )
            self._conn.commit()

    def add_token_usage(self, run_id: str, key: str, tokens: dict) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT token_usage FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row:
                usage = json.loads(row[0] or "{}")
                usage[key] = tokens
                self._conn.execute(
                    "UPDATE runs SET token_usage = ? WHERE id = ?",
                    (json.dumps(usage), run_id),
                )
                self._conn.commit()

    def clear_token_usage(self, run_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET token_usage = '{}' WHERE id = ?",
                (run_id,),
            )
            self._conn.commit()
