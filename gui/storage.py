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
                error_message TEXT,
                error_log_path TEXT
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

            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT UNIQUE NOT NULL,
                added_at TEXT NOT NULL,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                shares REAL NOT NULL,
                cost_basis_per_share REAL NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                closing_price REAL,
                account TEXT,
                notes TEXT
            );
            CREATE INDEX IF NOT EXISTS positions_ticker ON positions(ticker, closed_at);

            CREATE TABLE IF NOT EXISTS simulations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                base_run_id TEXT,
                ticker TEXT,
                scenario_json TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        _ensure_column(c, "runs", "error_log_path", "TEXT")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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
                 error: Optional[str] = None, error_log_path: Optional[str] = None) -> None:
    status = "error" if error else "done"
    with _conn() as c:
        c.execute(
            """UPDATE runs SET status=?, decision=?, log_path=?, error_message=?,
                              error_log_path=COALESCE(?, error_log_path),
                              completed_at=? WHERE run_id=?""",
            (status, decision, log_path, error, error_log_path, _now(), run_id),
        )


def write_run_error_log(
    *,
    run_id: str,
    meta: Dict[str, Any],
    message: str,
    traceback_text: Optional[str] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    stderr: Optional[List[str]] = None,
) -> Path:
    ticker = str(meta.get("ticker") or "UNKNOWN").strip().upper() or "UNKNOWN"
    trade_date = str(meta.get("trade_date") or "unknown")
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    path = DB_PATH.parent / "errors" / ticker / f"{run_id}__{trade_date}__{ts}.error.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "kind": "tradingagents-gui-error",
        "run_id": run_id,
        "message": message,
        "traceback": traceback_text or "",
        "metadata": meta,
        "recent_events": (events or [])[-200:],
        "stderr": stderr or [],
        "written_at": _now(),
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


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
        assert cur.lastrowid is not None
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
        assert cur.lastrowid is not None
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


# ---------------------------------------------------------------------------
# Watchlist (per-ticker subscription for live price/news streams)
# ---------------------------------------------------------------------------

def list_watchlist() -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM watchlist ORDER BY ticker"
        ).fetchall()
        return [dict(r) for r in rows]


def add_to_watchlist(ticker: str, notes: Optional[str] = None) -> Dict[str, Any]:
    ticker = ticker.strip().upper()
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO watchlist(ticker, added_at, notes) VALUES (?, ?, ?)",
            (ticker, _now(), notes),
        )
        if notes is not None:
            c.execute(
                "UPDATE watchlist SET notes=? WHERE ticker=?", (notes, ticker)
            )
        row = c.execute("SELECT * FROM watchlist WHERE ticker=?", (ticker,)).fetchone()
        return dict(row)


def remove_from_watchlist(ticker: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM watchlist WHERE ticker=?", (ticker.upper(),))


# ---------------------------------------------------------------------------
# Positions (long-form portfolio tracking)
# ---------------------------------------------------------------------------

def list_positions(*, include_closed: bool = False) -> List[Dict[str, Any]]:
    with _conn() as c:
        if include_closed:
            rows = c.execute("SELECT * FROM positions ORDER BY ticker, opened_at").fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM positions WHERE closed_at IS NULL ORDER BY ticker, opened_at"
            ).fetchall()
        return [dict(r) for r in rows]


def get_position(position_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM positions WHERE id=?", (position_id,)).fetchone()
        return dict(row) if row else None


def add_position(*, ticker: str, shares: float, cost_basis_per_share: float,
                 opened_at: Optional[str] = None, account: Optional[str] = None,
                 notes: Optional[str] = None) -> int:
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO positions(ticker, shares, cost_basis_per_share,
                                     opened_at, account, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ticker.upper(), float(shares), float(cost_basis_per_share),
             opened_at or _now(), account, notes),
        )
        assert cur.lastrowid is not None
        return int(cur.lastrowid)


def close_position(position_id: int, *, closing_price: float,
                   closed_at: Optional[str] = None) -> None:
    with _conn() as c:
        c.execute(
            """UPDATE positions SET closing_price=?, closed_at=? WHERE id=?""",
            (float(closing_price), closed_at or _now(), position_id),
        )


def update_position(position_id: int, *, shares: Optional[float] = None,
                    cost_basis_per_share: Optional[float] = None,
                    account: Optional[str] = None, notes: Optional[str] = None
                    ) -> None:
    fields = []
    args: List[Any] = []
    if shares is not None:
        fields.append("shares=?")
        args.append(float(shares))
    if cost_basis_per_share is not None:
        fields.append("cost_basis_per_share=?")
        args.append(float(cost_basis_per_share))
    if account is not None:
        fields.append("account=?")
        args.append(account)
    if notes is not None:
        fields.append("notes=?")
        args.append(notes)
    if not fields:
        return
    args.append(position_id)
    with _conn() as c:
        c.execute(f"UPDATE positions SET {', '.join(fields)} WHERE id=?", args)


def delete_position(position_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM positions WHERE id=?", (position_id,))


# ---------------------------------------------------------------------------
# Simulations
# ---------------------------------------------------------------------------

def list_simulations() -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM simulations ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def add_simulation(*, name: str, base_run_id: Optional[str], ticker: Optional[str],
                  scenario_json: str, result_json: str) -> int:
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO simulations(name, base_run_id, ticker,
                                       scenario_json, result_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, base_run_id, (ticker.upper() if ticker else None),
             scenario_json, result_json, _now()),
        )
        assert cur.lastrowid is not None
        return int(cur.lastrowid)


def get_simulation(sim_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM simulations WHERE id=?", (sim_id,)).fetchone()
        return dict(row) if row else None


def delete_simulation(sim_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM simulations WHERE id=?", (sim_id,))
