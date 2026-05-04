"""SQLite layer for notes and run metadata.

One file at ~/.tradingagents/gui.db with two tables:
- ``runs``: one row per analysis the GUI has launched. The actual debate
  transcript still lives on disk in ~/.tradingagents/logs/<TICKER>/...,
  this table just indexes them with status, costs, and the path back.
- ``notes``: free-text markdown notes. Optional fk to a run_id and/or
  ticker so notes attach to whatever the user is looking at.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

DB_PATH = Path.home() / ".tradingagents" / "gui.db"


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def init_db() -> None:
    """Create the database file and tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                provider TEXT,
                deep_model TEXT,
                quick_model TEXT,
                debate_rounds INTEGER,
                risk_rounds INTEGER,
                vendors_json TEXT,
                status TEXT NOT NULL,
                decision TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                llm_calls INTEGER DEFAULT 0,
                tool_calls INTEGER DEFAULT 0,
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                log_path TEXT,
                error_message TEXT
            );
            CREATE INDEX IF NOT EXISTS runs_ticker_date ON runs(ticker, trade_date);
            CREATE INDEX IF NOT EXISTS runs_started ON runs(started_at DESC);

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                run_id TEXT,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                tags TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS notes_ticker ON notes(ticker);
            CREATE INDEX IF NOT EXISTS notes_run ON notes(run_id);

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                model TEXT
            );
            CREATE INDEX IF NOT EXISTS chat_messages_run ON chat_messages(run_id, id);
            """
        )


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def new_run_id() -> str:
    return uuid.uuid4().hex


def create_run(
    *,
    run_id: str,
    ticker: str,
    trade_date: str,
    provider: str,
    deep_model: str,
    quick_model: str,
    debate_rounds: int,
    risk_rounds: int,
    vendors: Dict[str, str],
) -> None:
    with _conn() as c:
        c.execute(
            """
            INSERT INTO runs(run_id, ticker, trade_date, provider, deep_model,
                             quick_model, debate_rounds, risk_rounds, vendors_json,
                             status, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?)
            """,
            (
                run_id, ticker, trade_date, provider, deep_model, quick_model,
                debate_rounds, risk_rounds, json.dumps(vendors), _now(),
            ),
        )


def update_run_stats(run_id: str, *, llm_calls: int, tool_calls: int,
                    tokens_in: int, tokens_out: int) -> None:
    with _conn() as c:
        c.execute(
            """UPDATE runs SET llm_calls=?, tool_calls=?, tokens_in=?, tokens_out=?
               WHERE run_id=?""",
            (llm_calls, tool_calls, tokens_in, tokens_out, run_id),
        )


def finalize_run(run_id: str, *, decision: Optional[str], log_path: Optional[str],
                 error: Optional[str] = None) -> None:
    status = "error" if error else "done"
    with _conn() as c:
        c.execute(
            """UPDATE runs SET status=?, decision=?, log_path=?, error_message=?,
                              completed_at=? WHERE run_id=?""",
            (status, decision, log_path, error, _now(), run_id),
        )


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None


def list_runs(*, ticker: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    with _conn() as c:
        if ticker:
            rows = c.execute(
                "SELECT * FROM runs WHERE ticker=? ORDER BY started_at DESC LIMIT ?",
                (ticker, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def add_note(*, title: str, body: str, ticker: Optional[str] = None,
             run_id: Optional[str] = None, tags: Optional[str] = None) -> int:
    now = _now()
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO notes(ticker, run_id, title, body, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ticker, run_id, title, body, tags, now, now),
        )
        return int(cur.lastrowid)


def update_note(note_id: int, *, title: str, body: str, tags: Optional[str]) -> None:
    with _conn() as c:
        c.execute(
            """UPDATE notes SET title=?, body=?, tags=?, updated_at=? WHERE id=?""",
            (title, body, tags, _now(), note_id),
        )


def delete_note(note_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM notes WHERE id=?", (note_id,))


def list_notes(*, ticker: Optional[str] = None, run_id: Optional[str] = None,
               query: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM notes WHERE 1=1"
    args: List[Any] = []
    if ticker:
        sql += " AND ticker=?"
        args.append(ticker)
    if run_id:
        sql += " AND run_id=?"
        args.append(run_id)
    if query:
        sql += " AND (title LIKE ? OR body LIKE ? OR tags LIKE ?)"
        like = f"%{query}%"
        args.extend([like, like, like])
    sql += " ORDER BY updated_at DESC"
    with _conn() as c:
        rows = c.execute(sql, args).fetchall()
        return [dict(r) for r in rows]


def get_note(note_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Chat messages — one conversation per run_id, persisted across reloads.
# ---------------------------------------------------------------------------

def add_chat_message(*, run_id: str, role: str, content: str,
                     model: Optional[str] = None) -> int:
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO chat_messages(run_id, role, content, created_at, model)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, role, content, _now(), model),
        )
        return int(cur.lastrowid)


def list_chat_messages(run_id: str) -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM chat_messages WHERE run_id=? ORDER BY id ASC",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def clear_chat(run_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM chat_messages WHERE run_id=?", (run_id,))
