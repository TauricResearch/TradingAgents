"""
Database layer — SQLite via aiosqlite for async access.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

DB_PATH = os.getenv("TRADINGAGENTS_API_DB_PATH", "/data/db/tradingagents_api.db")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_column(
    db: aiosqlite.Connection,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    """Add a column if missing to support lightweight schema migrations."""
    async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
        cols = await cursor.fetchall()
    existing = {row[1] for row in cols}
    if column_name not in existing:
        await db.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"
        )


async def init_db(db_path: str = DB_PATH) -> None:
    db_parent = os.path.dirname(db_path)
    if db_parent:
        os.makedirs(db_parent, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id              TEXT PRIMARY KEY,
                ticker          TEXT NOT NULL,
                analysis_date   TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                submitted_at    TEXT NOT NULL,
                started_at      TEXT,
                completed_at    TEXT,
                recommendation  TEXT,
                analysis_file   TEXT,
                error_message   TEXT
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS batch_schedules (
                id              TEXT PRIMARY KEY,
                ticker          TEXT NOT NULL,
                llm_provider    TEXT NOT NULL,
                frequency       TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                last_run_at     TEXT,
                next_run_at     TEXT
            )
            """
        )

        await _ensure_column(db, "requests", "started_at", "TEXT")
        await _ensure_column(db, "requests", "llm_calls", "INTEGER")
        await _ensure_column(db, "requests", "tool_calls", "INTEGER")
        await _ensure_column(db, "requests", "tokens_in", "INTEGER")
        await _ensure_column(db, "requests", "tokens_out", "INTEGER")
        await _ensure_column(db, "requests", "total_tokens", "INTEGER")
        await _ensure_column(db, "requests", "llm_provider", "TEXT")
        await _ensure_column(db, "requests", "deep_model", "TEXT")
        await _ensure_column(db, "requests", "quick_model", "TEXT")
        await _ensure_column(db, "requests", "estimated_cost_usd", "REAL")
        await _ensure_column(db, "requests", "agent_recommendations", "TEXT")  # JSON serialized
        await _ensure_column(db, "requests", "llm_role_stats", "TEXT")  # JSON serialized
        await _ensure_column(db, "requests", "available_after", "TEXT")
        await _ensure_column(db, "requests", "deferred_for_quota", "INTEGER NOT NULL DEFAULT 0")
        await _ensure_column(db, "requests", "defer_reason", "TEXT")
        await _ensure_column(db, "batch_schedules", "last_run_at", "TEXT")
        await _ensure_column(db, "batch_schedules", "next_run_at", "TEXT")

        # Backfill legacy rows to be immediately eligible.
        await db.execute(
            """
            UPDATE requests
            SET available_after = COALESCE(available_after, submitted_at)
            WHERE available_after IS NULL
            """
        )

        # Backfill schedule next-run to now for existing rows.
        await db.execute(
            """
            UPDATE batch_schedules
            SET next_run_at = COALESCE(next_run_at, created_at)
            WHERE next_run_at IS NULL
            """
        )
        await db.commit()


async def create_batch_schedule(
    ticker: str,
    llm_provider: str,
    frequency: str,
    next_run_at: Optional[str] = None,
    db_path: str = DB_PATH,
) -> str:
    schedule_id = str(uuid.uuid4())
    now = _now_iso()
    first_run = next_run_at or now
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO batch_schedules (id, ticker, llm_provider, frequency, created_at, updated_at, next_run_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (schedule_id, ticker.upper(), llm_provider.lower(), frequency.lower(), now, now, first_run),
        )
        await db.commit()
    return schedule_id


async def list_batch_schedules(db_path: str = DB_PATH) -> list[dict]:
    """List batch schedules with latest matching request metadata."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                b.id,
                b.ticker,
                b.llm_provider,
                b.frequency,
                b.created_at,
                b.updated_at,
                b.last_run_at,
                b.next_run_at,
                r.id AS latest_request_id,
                r.recommendation AS latest_recommendation,
                r.submitted_at AS latest_submitted_at,
                r.completed_at AS latest_completed_at,
                r.analysis_file AS latest_analysis_file,
                r.status AS latest_request_status
            FROM batch_schedules b
            LEFT JOIN requests r ON r.id = (
                SELECT r2.id
                FROM requests r2
                WHERE r2.ticker = b.ticker
                  AND lower(COALESCE(r2.llm_provider, 'ollama')) = lower(b.llm_provider)
                ORDER BY r2.submitted_at DESC
                LIMIT 1
            )
            ORDER BY b.updated_at DESC
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_recommendation_history(
    ticker: str,
    llm_provider: Optional[str] = None,
    limit: int = 50,
    db_path: str = DB_PATH,
) -> list[dict]:
    """Return recent completed recommendation history for a ticker/provider."""
    safe_limit = max(1, min(int(limit), 200))
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if llm_provider:
            async with db.execute(
                """
                SELECT id, ticker, llm_provider, analysis_date, completed_at, recommendation
                FROM requests
                WHERE status='completed'
                  AND ticker=?
                  AND lower(COALESCE(llm_provider, ''))=lower(?)
                ORDER BY completed_at DESC
                LIMIT ?
                """,
                (ticker.upper(), llm_provider.lower(), safe_limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

        async with db.execute(
            """
            SELECT id, ticker, llm_provider, analysis_date, completed_at, recommendation
            FROM requests
            WHERE status='completed'
              AND ticker=?
            ORDER BY completed_at DESC
            LIMIT ?
            """,
            (ticker.upper(), safe_limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def list_due_batch_schedules(now_iso: str, db_path: str = DB_PATH) -> list[dict]:
    """Return schedule rows that are due to run now."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, ticker, llm_provider, frequency, last_run_at, next_run_at
            FROM batch_schedules
            WHERE next_run_at IS NOT NULL AND next_run_at <= ?
            ORDER BY next_run_at ASC
            """,
            (now_iso,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def update_batch_schedule_run(
    schedule_id: str,
    last_run_at: str,
    next_run_at: str,
    db_path: str = DB_PATH,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            UPDATE batch_schedules
            SET last_run_at = ?, next_run_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (last_run_at, next_run_at, _now_iso(), schedule_id),
        )
        await db.commit()


async def mark_stale_running_requests(
    reason: str = "Request interrupted by service restart",
    db_path: str = DB_PATH,
) -> None:
    """Convert lingering running rows to failed on startup."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            UPDATE requests
            SET status='failed', completed_at=?, error_message=?
            WHERE status='running'
            """,
            (_now_iso(), reason),
        )
        await db.commit()


async def create_request(
    ticker: str,
    analysis_date: str,
    llm_provider: str = "ollama",
    available_after: Optional[str] = None,
    db_path: str = DB_PATH,
) -> str:
    req_id = str(uuid.uuid4())
    submitted_at = _now_iso()
    eligible_at = available_after or submitted_at
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO requests (id, ticker, analysis_date, llm_provider, status, submitted_at, available_after, deferred_for_quota)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, 0)
            """,
            (req_id, ticker.upper(), analysis_date, llm_provider.lower(), submitted_at, eligible_at),
        )
        await db.commit()
    return req_id


async def get_request(req_id: str, db_path: str = DB_PATH) -> Optional[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM requests WHERE id = ?", (req_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def list_requests(status_filter: Optional[str], db_path: str = DB_PATH) -> list[dict]:
    """Return requests filtered by status group.
    status_filter='open'   → pending + running
    status_filter='completed' → completed only
    status_filter='closed' → completed + failed
    None                   → all
    """
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if status_filter == "open":
            sql = "SELECT * FROM requests WHERE status IN ('pending','running') ORDER BY submitted_at DESC"
            args: tuple = ()
        elif status_filter == "completed":
            sql = "SELECT * FROM requests WHERE status = 'completed' ORDER BY completed_at DESC"
            args = ()
        elif status_filter == "closed":
            sql = "SELECT * FROM requests WHERE status IN ('completed','failed','canceled') ORDER BY completed_at DESC"
            args = ()
        else:
            sql = "SELECT * FROM requests ORDER BY submitted_at DESC"
            args = ()
        async with db.execute(sql, args) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def update_request_running(req_id: str, db_path: str = DB_PATH) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            UPDATE requests
            SET status='running', started_at=?
            WHERE id=? AND status='pending' AND (available_after IS NULL OR available_after <= ?)
            """,
            (_now_iso(), req_id, _now_iso()),
        )
        await db.commit()
        return cursor.rowcount > 0


async def update_request_completed(
    req_id: str,
    recommendation: str,
    analysis_file: str,
    llm_provider: Optional[str] = None,
    deep_model: Optional[str] = None,
    quick_model: Optional[str] = None,
    estimated_cost_usd: Optional[float] = None,
    stats: Optional[dict] = None,
    agent_recommendations: Optional[dict] = None,
    llm_role_stats: Optional[dict] = None,
    db_path: str = DB_PATH,
) -> None:
    llm_calls = int((stats or {}).get("llm_calls", 0))
    tool_calls = int((stats or {}).get("tool_calls", 0))
    tokens_in = int((stats or {}).get("tokens_in", 0))
    tokens_out = int((stats or {}).get("tokens_out", 0))
    total_tokens = int((stats or {}).get("total_tokens", tokens_in + tokens_out))
    agent_recommendations_json = json.dumps(agent_recommendations or {}) if agent_recommendations else None
    llm_role_stats_json = json.dumps(llm_role_stats or {}) if llm_role_stats else None

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            UPDATE requests
            SET status='completed', completed_at=?, recommendation=?, analysis_file=?,
                llm_calls=?, tool_calls=?, tokens_in=?, tokens_out=?, total_tokens=?,
                llm_provider=COALESCE(?, llm_provider), deep_model=?, quick_model=?, estimated_cost_usd=?,
                agent_recommendations=?, llm_role_stats=?, deferred_for_quota=0, defer_reason=NULL
            WHERE id=? AND status='running'
            """,
            (
                _now_iso(),
                recommendation,
                analysis_file,
                llm_calls,
                tool_calls,
                tokens_in,
                tokens_out,
                total_tokens,
                llm_provider.lower() if llm_provider else None,
                deep_model,
                quick_model,
                estimated_cost_usd,
                agent_recommendations_json,
                llm_role_stats_json,
                req_id,
            ),
        )
        await db.commit()


async def update_request_failed(
    req_id: str, error_message: str, db_path: str = DB_PATH
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            UPDATE requests
            SET status='failed', completed_at=?, error_message=?
            WHERE id=? AND status='running'
            """,
            (_now_iso(), error_message, req_id),
        )
        await db.commit()


async def reschedule_running_request(
    req_id: str,
    available_after: str,
    reason: str,
    deferred_for_quota: int,
    analysis_date: Optional[str] = None,
    db_path: str = DB_PATH,
) -> bool:
    """Move a running request back to pending with a future availability time."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            UPDATE requests
            SET status='pending',
                started_at=NULL,
                available_after=?,
                deferred_for_quota=?,
                defer_reason=?,
                analysis_date=COALESCE(?, analysis_date)
            WHERE id=? AND status='running'
            """,
            (available_after, int(deferred_for_quota), reason, analysis_date, req_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def list_due_pending_requests(now_iso: str, db_path: str = DB_PATH) -> list[dict]:
    """Pending requests that are eligible to be run now, deferred quota items first."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT *
            FROM requests
            WHERE status='pending' AND (available_after IS NULL OR available_after <= ?)
            ORDER BY deferred_for_quota DESC, submitted_at ASC
            """,
            (now_iso,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_google_llm_calls_used_between(
    start_iso: str,
    end_iso: str,
    db_path: str = DB_PATH,
) -> int:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            """
            SELECT COALESCE(SUM(COALESCE(llm_calls, 0)), 0)
            FROM requests
            WHERE status='completed'
              AND lower(COALESCE(llm_provider, ''))='google'
              AND completed_at >= ?
              AND completed_at < ?
            """,
            (start_iso, end_iso),
        ) as cursor:
            row = await cursor.fetchone()
            return int(row[0] if row and row[0] is not None else 0)


async def get_llm_calls_by_provider_between(
    start_iso: str,
    end_iso: str,
    db_path: str = DB_PATH,
) -> list[dict]:
    """Aggregate completed llm_calls by provider in a time window."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                lower(COALESCE(NULLIF(llm_provider, ''), 'unknown')) AS llm_provider,
                COALESCE(SUM(COALESCE(llm_calls, 0)), 0) AS llm_calls
            FROM requests
            WHERE status = 'completed'
              AND completed_at >= ?
              AND completed_at < ?
            GROUP BY lower(COALESCE(NULLIF(llm_provider, ''), 'unknown'))
            ORDER BY llm_calls DESC, llm_provider ASC
            """,
            (start_iso, end_iso),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_llm_usage_by_provider_between(
    start_iso: str,
    end_iso: str,
    db_path: str = DB_PATH,
) -> list[dict]:
    """Aggregate completed provider usage (calls and tokens) in a time window."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                lower(COALESCE(NULLIF(llm_provider, ''), 'unknown')) AS llm_provider,
                COALESCE(SUM(COALESCE(llm_calls, 0)), 0) AS llm_calls,
                COALESCE(SUM(COALESCE(tokens_in, 0)), 0) AS tokens_in,
                COALESCE(SUM(COALESCE(tokens_out, 0)), 0) AS tokens_out,
                COALESCE(SUM(COALESCE(total_tokens, COALESCE(tokens_in,0) + COALESCE(tokens_out,0))), 0) AS total_tokens
            FROM requests
            WHERE status = 'completed'
              AND completed_at >= ?
              AND completed_at < ?
            GROUP BY lower(COALESCE(NULLIF(llm_provider, ''), 'unknown'))
            ORDER BY llm_calls DESC, llm_provider ASC
            """,
            (start_iso, end_iso),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_llm_role_stats_between(
    start_iso: str,
    end_iso: str,
    db_path: str = DB_PATH,
) -> list[dict]:
    """Aggregate completed per-role LLM stats in a time window.

    Role-level data is persisted per request as JSON in requests.llm_role_stats.
    """
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT llm_role_stats
            FROM requests
            WHERE status = 'completed'
              AND completed_at >= ?
              AND completed_at < ?
              AND llm_role_stats IS NOT NULL
              AND trim(llm_role_stats) <> ''
            """,
            (start_iso, end_iso),
        ) as cursor:
            rows = await cursor.fetchall()

    merged: dict[str, dict] = {}
    for row in rows:
        payload = row["llm_role_stats"]
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(parsed, dict):
            continue

        for role, stats in parsed.items():
            if not isinstance(stats, dict):
                continue
            key = str(role or "unknown").strip().lower() or "unknown"
            bucket = merged.setdefault(
                key,
                {
                    "role": key,
                    "llm_calls": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "total_tokens": 0,
                    "total_duration_seconds": 0.0,
                },
            )
            bucket["llm_calls"] += int(stats.get("llm_calls", 0) or 0)
            bucket["tokens_in"] += int(stats.get("tokens_in", 0) or 0)
            bucket["tokens_out"] += int(stats.get("tokens_out", 0) or 0)
            bucket["total_tokens"] += int(stats.get("total_tokens", 0) or 0)
            bucket["total_duration_seconds"] += float(stats.get("total_duration_seconds", 0.0) or 0.0)

    items: list[dict] = []
    for role, stats in merged.items():
        calls = int(stats["llm_calls"])
        duration = float(stats["total_duration_seconds"])
        items.append(
            {
                "role": role,
                "llm_calls": calls,
                "tokens_in": int(stats["tokens_in"]),
                "tokens_out": int(stats["tokens_out"]),
                "total_tokens": int(stats["total_tokens"]),
                "total_duration_seconds": duration,
                "avg_duration_seconds": (duration / calls) if calls else 0.0,
            }
        )

    return sorted(items, key=lambda x: (-x["llm_calls"], x["role"]))


async def defer_due_google_pending_requests(
    now_iso: str,
    available_after_iso: str,
    reason: str,
    db_path: str = DB_PATH,
) -> int:
    """Defer all due Google pending requests until the specified timestamp."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            UPDATE requests
            SET available_after=?, deferred_for_quota=1, defer_reason=?
            WHERE status='pending'
              AND lower(COALESCE(llm_provider, ''))='google'
                            AND (available_after IS NULL OR available_after <= ?)
            """,
                        (available_after_iso, reason, now_iso),
        )
        await db.commit()
        return cursor.rowcount


async def cancel_request(req_id: str, db_path: str = DB_PATH) -> bool:
    """Cancel an open request.
    Returns True if request moved to canceled, False otherwise.
    """
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            UPDATE requests
            SET status='canceled', completed_at=?, error_message=?
            WHERE id=? AND status IN ('pending','running')
            """,
            (_now_iso(), "Canceled by user", req_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def cancel_all_open_requests(db_path: str = DB_PATH) -> int:
    """Cancel all pending/running requests and return number canceled."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            UPDATE requests
            SET status='canceled', completed_at=?, error_message=?
            WHERE status IN ('pending','running')
            """,
            (_now_iso(), "Canceled by user"),
        )
        await db.commit()
        return cursor.rowcount


async def delete_incomplete_requests(db_path: str = DB_PATH) -> int:
    """Delete all incomplete analysis records (status not 'completed').
    
    Removes all requests with status in: 'pending', 'running', 'failed', 'canceled'.
    Only keeps successfully completed analyses.
    
    Returns the number of records deleted.
    """
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            DELETE FROM requests
            WHERE status IN ('pending', 'running', 'failed', 'canceled')
            """
        )
        await db.commit()
        return cursor.rowcount
