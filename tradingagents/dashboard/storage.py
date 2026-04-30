from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .extract import dump_record, load_record
from .models import AnalysisRecord


class AnalysisRepository:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.runs_dir = self.base_dir / "runs"
        self.db_path = self.base_dir / "dashboard.db"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    run_id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    trader_action TEXT NOT NULL,
                    research_recommendation TEXT NOT NULL,
                    decision_summary TEXT NOT NULL,
                    structured_path TEXT NOT NULL,
                    raw_log_path TEXT NOT NULL,
                    payload_path TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def payload_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def save(self, record: AnalysisRecord) -> AnalysisRecord:
        payload_path = self.payload_path(record["run_id"])
        materialized = dict(record)
        materialized["structured_path"] = str(payload_path)
        payload_path.write_text(dump_record(materialized), encoding="utf-8")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analyses (
                    run_id, ticker, trade_date, generated_at, rating, trader_action,
                    research_recommendation, decision_summary, structured_path,
                    raw_log_path, payload_path, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    ticker=excluded.ticker,
                    trade_date=excluded.trade_date,
                    generated_at=excluded.generated_at,
                    rating=excluded.rating,
                    trader_action=excluded.trader_action,
                    research_recommendation=excluded.research_recommendation,
                    decision_summary=excluded.decision_summary,
                    structured_path=excluded.structured_path,
                    raw_log_path=excluded.raw_log_path,
                    payload_path=excluded.payload_path,
                    payload_json=excluded.payload_json
                """,
                (
                    materialized["run_id"],
                    materialized["ticker"],
                    materialized["trade_date"],
                    materialized["generated_at"],
                    materialized["rating"],
                    materialized["trader_action"],
                    materialized["research_recommendation"],
                    materialized["decision_summary"],
                    materialized["structured_path"],
                    materialized["raw_log_path"],
                    str(payload_path),
                    json.dumps(materialized, ensure_ascii=False),
                ),
            )
            connection.commit()
        return materialized

    def list_runs(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id, ticker, trade_date, generated_at, rating,
                       trader_action, research_recommendation, decision_summary,
                       structured_path, raw_log_path
                FROM analyses
                ORDER BY generated_at DESC, ticker ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> Optional[AnalysisRecord]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_path FROM analyses WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return load_record(row["payload_path"])

    def latest_generated_at(self) -> Optional[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT MAX(generated_at) AS generated_at FROM analyses"
            ).fetchone()
        return row["generated_at"] if row and row["generated_at"] else None
