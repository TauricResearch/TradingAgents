import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import settings


class Database:
    def __init__(self, db_path: Path = settings.DB_PATH):
        self.db_path = db_path
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for high-concurrency read/write
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.get_connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                asset_type TEXT DEFAULT 'stock',
                analysts TEXT NOT NULL,
                llm_provider TEXT NOT NULL,
                deep_think_llm TEXT NOT NULL,
                quick_think_llm TEXT NOT NULL,
                max_debate_rounds INTEGER DEFAULT 1,
                max_risk_discuss_rounds INTEGER DEFAULT 1,
                output_language TEXT DEFAULT 'English',
                status TEXT NOT NULL,
                progress INTEGER DEFAULT 0,
                current_stage TEXT DEFAULT 'Queued',
                decision_signal TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                duration_seconds REAL
            );

            CREATE TABLE IF NOT EXISTS job_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS job_reports (
                job_id TEXT PRIMARY KEY,
                final_state TEXT NOT NULL,
                complete_report_md TEXT,
                executive_summary TEXT,
                recommendation TEXT,
                entry_price REAL,
                stop_loss REAL,
                target_price REAL,
                market_report_md TEXT,
                sentiment_report_md TEXT,
                news_report_md TEXT,
                fundamentals_report_md TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id, id ASC);
            """)

    # Jobs Operations
    def create_job(self, job_dict: dict[str, Any]) -> dict[str, Any]:
        data = dict(job_dict)
        if isinstance(data.get("analysts"), list):
            data["analysts"] = json.dumps(data["analysts"])
        elif not data.get("analysts"):
            data["analysts"] = json.dumps(["market", "social", "news", "fundamentals"])
        data.setdefault("asset_type", "stock")
        data.setdefault("llm_provider", "openai")
        data.setdefault("deep_think_llm", "gpt-5.6")
        data.setdefault("quick_think_llm", "gpt-5.6-luna")
        data.setdefault("max_debate_rounds", 1)
        data.setdefault("max_risk_discuss_rounds", 1)
        data.setdefault("output_language", "English")
        data.setdefault("status", "queued")
        data.setdefault("progress", 0)
        data.setdefault("current_stage", "Queued")
        data.setdefault("created_at", datetime.utcnow().isoformat())
        with self.get_connection() as conn:
            conn.execute("""
            INSERT OR REPLACE INTO jobs (
                id, ticker, trade_date, asset_type, analysts,
                llm_provider, deep_think_llm, quick_think_llm,
                max_debate_rounds, max_risk_discuss_rounds, output_language,
                status, progress, current_stage, created_at
            ) VALUES (
                :id, :ticker, :trade_date, :asset_type, :analysts,
                :llm_provider, :deep_think_llm, :quick_think_llm,
                :max_debate_rounds, :max_risk_discuss_rounds, :output_language,
                :status, :progress, :current_stage, :created_at
            )
            """, data)
            conn.commit()
        return job_dict

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return None
            res = dict(row)
            res["analysts"] = json.loads(res["analysts"]) if res.get("analysts") else []
            return res

    def list_jobs(self, limit: int = 50, offset: int = 0, status: str | None = None) -> list[dict[str, Any]]:
        with self.get_connection() as conn:
            if status:
                cursor = conn.execute(
                    "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                    (status, limit, offset)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                    (limit, offset)
                )
            rows = cursor.fetchall()
            result = []
            for r in rows:
                item = dict(r)
                item["analysts"] = json.loads(item["analysts"]) if item.get("analysts") else []
                result.append(item)
            return result

    def count_jobs(self, status: str | None = None) -> int:
        with self.get_connection() as conn:
            if status:
                row = conn.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status = ?", (status,)).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) as cnt FROM jobs").fetchone()
            return int(row["cnt"]) if row else 0

    def update_job_status(
        self,
        job_id: str,
        status: str,
        progress: int | None = None,
        current_stage: str | None = None,
        decision_signal: str | None = None,
        error_message: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        duration_seconds: float | None = None
    ):
        updates = ["status = :status"]
        params: dict[str, Any] = {"job_id": job_id, "status": status}

        if progress is not None:
            updates.append("progress = :progress")
            params["progress"] = progress
        if current_stage is not None:
            updates.append("current_stage = :current_stage")
            params["current_stage"] = current_stage
        if decision_signal is not None:
            updates.append("decision_signal = :decision_signal")
            params["decision_signal"] = decision_signal
        if error_message is not None:
            updates.append("error_message = :error_message")
            params["error_message"] = error_message
        if started_at is not None:
            updates.append("started_at = :started_at")
            params["started_at"] = started_at
        if completed_at is not None:
            updates.append("completed_at = :completed_at")
            params["completed_at"] = completed_at
        if duration_seconds is not None:
            updates.append("duration_seconds = :duration_seconds")
            params["duration_seconds"] = duration_seconds

        sql = f"UPDATE jobs SET {', '.join(updates)} WHERE id = :job_id"
        with self.get_connection() as conn:
            conn.execute(sql, params)
            conn.commit()

    # Events Operations
    def add_event(self, job_id: str, event_type: str, data: dict[str, Any]):
        now = datetime.utcnow().isoformat() + "Z"
        with self.get_connection() as conn:
            conn.execute("""
            INSERT INTO job_events (job_id, timestamp, event_type, data)
            VALUES (?, ?, ?, ?)
            """, (job_id, now, event_type, json.dumps(data, ensure_ascii=False)))
            conn.commit()

    def get_events(self, job_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, event_type, data FROM job_events WHERE job_id = ? AND id > ? ORDER BY id ASC",
                (job_id, after_id)
            ).fetchall()
            result = []
            for r in rows:
                result.append({
                    "id": r["id"],
                    "job_id": job_id,
                    "timestamp": r["timestamp"],
                    "event_type": r["event_type"],
                    "data": json.loads(r["data"]) if r["data"] else {}
                })
            return result

    # Reports Operations
    def save_report(self, report_dict: dict[str, Any]):
        data = dict(report_dict)
        data.setdefault("final_state", "{}")
        data.setdefault("complete_report_md", "")
        data.setdefault("executive_summary", "")
        data.setdefault("recommendation", None)
        data.setdefault("entry_price", None)
        data.setdefault("stop_loss", None)
        data.setdefault("target_price", None)
        data.setdefault("market_report_md", "")
        data.setdefault("sentiment_report_md", "")
        data.setdefault("news_report_md", "")
        data.setdefault("fundamentals_report_md", "")
        with self.get_connection() as conn:
            conn.execute("""
            INSERT OR REPLACE INTO job_reports (
                job_id, final_state, complete_report_md, executive_summary,
                recommendation, entry_price, stop_loss, target_price,
                market_report_md, sentiment_report_md, news_report_md, fundamentals_report_md
            ) VALUES (
                :job_id, :final_state, :complete_report_md, :executive_summary,
                :recommendation, :entry_price, :stop_loss, :target_price,
                :market_report_md, :sentiment_report_md, :news_report_md, :fundamentals_report_md
            )
            """, data)
            conn.commit()

    def get_report(self, job_id: str) -> dict[str, Any] | None:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM job_reports WHERE job_id = ?", (job_id,)).fetchone()
            if not row:
                return None
            res = dict(row)
            if res.get("final_state"):
                res["final_state"] = json.loads(res["final_state"])
            return res

db = Database()
