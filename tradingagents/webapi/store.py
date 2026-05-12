from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .schemas import AnalysisRequest, SettingsPayload
from .service import API_KEY_ENV_BY_PROVIDER, mask_secret


def default_db_path() -> Path:
    return Path(
        os.getenv(
            "TRADINGAGENTS_WEB_DB",
            str(Path.home() / ".tradingagents" / "web" / "tradingagents_web.sqlite3"),
        )
    )


class SQLiteWebStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    company_name TEXT,
                    analysis_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    decision TEXT,
                    title TEXT NOT NULL,
                    request_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_events (
                    id TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_run_events_run_id_sequence
                    ON run_events(run_id, sequence);

                CREATE TABLE IF NOT EXISTS app_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    settings_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS api_keys (
                    provider TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def save_run(self, run: Dict[str, Any], request: AnalysisRequest) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    id, ticker, company_name, analysis_date, status,
                    created_at, updated_at, decision, title, request_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run["id"],
                    run["ticker"],
                    run.get("company_name"),
                    run["analysis_date"],
                    run["status"],
                    run["created_at"],
                    run["updated_at"],
                    run.get("decision"),
                    run["title"],
                    request.model_dump_json(),
                ),
            )

    def update_run(self, run_id: str, **updates: Any) -> None:
        allowed = {"status", "updated_at", "decision"}
        fields = [(key, value) for key, value in updates.items() if key in allowed]
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key, _ in fields)
        values = [value for _, value in fields]
        values.append(run_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE runs SET {assignments} WHERE id = ?", values)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._row_to_run(row) if row else None

    def list_runs(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
        return [self._row_to_run(row) for row in rows]

    def get_request(self, run_id: str) -> Optional[AnalysisRequest]:
        with self._connect() as conn:
            row = conn.execute("SELECT request_json FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return AnalysisRequest.model_validate_json(row["request_json"])

    def append_event(self, run_id: str, event: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO run_events (id, run_id, event_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event["id"],
                    run_id,
                    json.dumps(event, ensure_ascii=False),
                    event["createdAt"],
                ),
            )

    def get_events(self, run_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_json FROM run_events WHERE run_id = ? ORDER BY sequence ASC",
                (run_id,),
            ).fetchall()
        return [json.loads(row["event_json"]) for row in rows]

    def delete_run(self, run_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        return cursor.rowcount > 0

    def save_settings(self, settings: SettingsPayload) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (id, settings_json) VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET settings_json = excluded.settings_json
                """,
                (settings.model_dump_json(),),
            )

    def get_settings(self) -> SettingsPayload:
        with self._connect() as conn:
            row = conn.execute("SELECT settings_json FROM app_settings WHERE id = 1").fetchone()
        if not row:
            return SettingsPayload()
        return SettingsPayload.model_validate_json(row["settings_json"])

    def save_api_key(self, provider: str, value: str) -> Dict[str, str]:
        provider_key = provider.strip().lower()
        if provider_key not in API_KEY_ENV_BY_PROVIDER:
            raise KeyError(provider_key)
        cleaned = value.strip()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO api_keys (provider, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(provider) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (provider_key, cleaned),
            )
        os.environ[API_KEY_ENV_BY_PROVIDER[provider_key]] = cleaned
        return {"provider": provider_key, "masked": mask_secret(cleaned)}

    def get_api_key(self, provider: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM api_keys WHERE provider = ?",
                (provider.strip().lower(),),
            ).fetchone()
        return row["value"] if row else ""

    def get_masked_api_keys(self) -> Dict[str, str]:
        return {
            provider: mask_secret(self.get_api_key(provider) or os.environ.get(env_name, ""))
            for provider, env_name in API_KEY_ENV_BY_PROVIDER.items()
        }

    def apply_api_keys_to_env(self, setter: Callable[[str, str], Any] = os.environ.__setitem__) -> None:
        with self._connect() as conn:
            rows = conn.execute("SELECT provider, value FROM api_keys").fetchall()
        for row in rows:
            env_name = API_KEY_ENV_BY_PROVIDER.get(row["provider"])
            if env_name:
                setter(env_name, row["value"])

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "ticker": row["ticker"],
            "company_name": row["company_name"],
            "analysis_date": row["analysis_date"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "decision": row["decision"],
            "title": row["title"],
        }
