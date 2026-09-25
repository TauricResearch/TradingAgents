"""SQLite storage backend for multi-user crypto trading memory.

The schema intentionally keeps the existing JSON payloads while adding indexed
columns for the fields the dashboard needs.  This makes the migration from the
old JSON/JSONL files safe and incremental: current code can still read/write the
same dictionaries, while multiple users and shared memory spaces are managed in
SQL tables.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_USER_ID = "admin"
DEFAULT_MEMORY_SPACE_ID = "default"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class SQLiteTradingStore:
    """Small SQLite repository used by dashboard, paper trading, and memory.

    Concepts:
    - ``users``: local users.  The default deployment creates an ``admin`` user.
    - ``memory_spaces``: reusable memory pools.  A space can be shared by many
      users or kept private.
    - ``memory_selection``: per-user mode selection.  Only admins may select the
      memory space used for trade mode.
    - ``memory_items``: raw/lesson/global memory rows.
    - paper tables: account, positions, closed trades, candidates, approvals.
    """

    def __init__(self, db_path: str | Path, user_id: str = DEFAULT_USER_ID):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_id = user_id or DEFAULT_USER_ID
        self._init_schema()
        self.ensure_default_records()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_spaces (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'shared' CHECK(scope IN ('private', 'shared')),
                    description TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(created_by) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS user_memory_access (
                    user_id TEXT NOT NULL,
                    memory_space_id TEXT NOT NULL,
                    access_level TEXT NOT NULL CHECK(access_level IN ('read', 'write', 'admin')),
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, memory_space_id),
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(memory_space_id) REFERENCES memory_spaces(id)
                );

                CREATE TABLE IF NOT EXISTS memory_selection (
                    user_id TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK(mode IN ('training', 'trade')),
                    memory_space_id TEXT NOT NULL,
                    selected_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, mode),
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(memory_space_id) REFERENCES memory_spaces(id),
                    FOREIGN KEY(selected_by) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS dashboard_state (
                    user_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY,
                    memory_space_id TEXT NOT NULL,
                    tier TEXT NOT NULL CHECK(tier IN ('raw', 'lesson', 'global')),
                    symbol TEXT,
                    trade_date TEXT,
                    status TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(memory_space_id) REFERENCES memory_spaces(id)
                );
                CREATE INDEX IF NOT EXISTS idx_memory_items_lookup
                    ON memory_items(memory_space_id, tier, symbol, created_at);

                CREATE TABLE IF NOT EXISTS paper_accounts (
                    user_id TEXT NOT NULL,
                    memory_space_id TEXT NOT NULL,
                    account_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, memory_space_id),
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(memory_space_id) REFERENCES memory_spaces(id)
                );

                CREATE TABLE IF NOT EXISTS paper_positions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    memory_space_id TEXT NOT NULL,
                    symbol TEXT,
                    strategy TEXT,
                    opened_at TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(memory_space_id) REFERENCES memory_spaces(id)
                );
                CREATE INDEX IF NOT EXISTS idx_paper_positions_owner
                    ON paper_positions(user_id, memory_space_id, symbol);

                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    memory_space_id TEXT NOT NULL,
                    symbol TEXT,
                    strategy TEXT,
                    result TEXT,
                    pnl_usdt REAL,
                    opened_at TEXT,
                    closed_at TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(memory_space_id) REFERENCES memory_spaces(id)
                );
                CREATE INDEX IF NOT EXISTS idx_paper_trades_owner
                    ON paper_trades(user_id, memory_space_id, closed_at DESC);

                CREATE TABLE IF NOT EXISTS scan_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    memory_space_id TEXT NOT NULL,
                    symbol TEXT,
                    strategy TEXT,
                    scanned_at TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(memory_space_id) REFERENCES memory_spaces(id)
                );
                CREATE INDEX IF NOT EXISTS idx_scan_candidates_owner
                    ON scan_candidates(user_id, memory_space_id, scanned_at DESC);

                CREATE TABLE IF NOT EXISTS pending_approvals (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    memory_space_id TEXT NOT NULL,
                    symbol TEXT,
                    status TEXT,
                    created_at TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(memory_space_id) REFERENCES memory_spaces(id)
                );

                CREATE TABLE IF NOT EXISTS processed_signal_keys (
                    user_id TEXT NOT NULL,
                    memory_space_id TEXT NOT NULL,
                    signal_key TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, memory_space_id, signal_key),
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(memory_space_id) REFERENCES memory_spaces(id)
                );
                """
            )

    def ensure_default_records(self) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users(id, username, role, created_at) VALUES (?, ?, 'admin', ?)",
                (DEFAULT_USER_ID, DEFAULT_USER_ID, now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_spaces(id, name, scope, description, created_by, created_at)
                VALUES (?, 'Default shared memory', 'shared', 'Default shared TradingAgents crypto memory', ?, ?)
                """,
                (DEFAULT_MEMORY_SPACE_ID, DEFAULT_USER_ID, now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO user_memory_access(user_id, memory_space_id, access_level, created_at)
                VALUES (?, ?, 'admin', ?)
                """,
                (DEFAULT_USER_ID, DEFAULT_MEMORY_SPACE_ID, now),
            )
            for mode in ("training", "trade"):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO memory_selection(user_id, mode, memory_space_id, selected_by, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (DEFAULT_USER_ID, mode, DEFAULT_MEMORY_SPACE_ID, DEFAULT_USER_ID, now),
                )

    def ensure_user(self, user_id: str, role: str = "user") -> None:
        role = role if role in {"admin", "user"} else "user"
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users(id, username, role, created_at) VALUES (?, ?, ?, ?)",
                (user_id, user_id, role, _utc_now()),
            )

    def is_admin(self, user_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        return bool(row and row["role"] == "admin")

    def list_memory_spaces(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM memory_spaces ORDER BY name").fetchall()
        return [dict(row) for row in rows]

    def create_memory_space(self, name: str, created_by: str = DEFAULT_USER_ID, scope: str = "shared", description: str = "") -> str:
        if not self.is_admin(created_by):
            raise PermissionError("Only admin users can create shared trading memory spaces")
        memory_space_id = str(uuid.uuid4())
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_spaces(id, name, scope, description, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (memory_space_id, name, scope if scope in {"private", "shared"} else "shared", description, created_by, now),
            )
            conn.execute(
                """
                INSERT INTO user_memory_access(user_id, memory_space_id, access_level, created_at)
                VALUES (?, ?, 'admin', ?)
                """,
                (created_by, memory_space_id, now),
            )
        return memory_space_id

    def selected_memory_space(self, user_id: str, mode: str = "training") -> str:
        mode = mode if mode in {"training", "trade"} else "training"
        with self.connect() as conn:
            row = conn.execute(
                "SELECT memory_space_id FROM memory_selection WHERE user_id = ? AND mode = ?",
                (user_id, mode),
            ).fetchone()
        return str(row["memory_space_id"]) if row else DEFAULT_MEMORY_SPACE_ID

    def set_memory_selection(self, user_id: str, mode: str, memory_space_id: str, actor_user_id: str) -> None:
        mode = mode if mode in {"training", "trade"} else "training"
        if mode == "trade" and not self.is_admin(actor_user_id):
            raise PermissionError("Only admin users can select the memory used for trade mode")
        self.ensure_user(user_id)
        now = _utc_now()
        with self.connect() as conn:
            exists = conn.execute("SELECT 1 FROM memory_spaces WHERE id = ?", (memory_space_id,)).fetchone()
            if not exists:
                raise ValueError(f"Unknown memory_space_id: {memory_space_id}")
            conn.execute(
                """
                INSERT INTO memory_selection(user_id, mode, memory_space_id, selected_by, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, mode) DO UPDATE SET
                    memory_space_id=excluded.memory_space_id,
                    selected_by=excluded.selected_by,
                    updated_at=excluded.updated_at
                """,
                (user_id, mode, memory_space_id, actor_user_id, now),
            )

    def load_dashboard_state(self, user_id: str) -> Dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT state_json FROM dashboard_state WHERE user_id = ?", (user_id,)).fetchone()
        return _json_loads(row["state_json"], {}) if row else {}

    def save_dashboard_state(self, user_id: str, state: Dict[str, Any]) -> None:
        now = _utc_now()
        self.ensure_user(user_id)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO dashboard_state(user_id, state_json, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at
                """,
                (user_id, _json_dumps(state), now),
            )

    def append_memory(self, tier: str, record: Dict[str, Any], memory_space_id: str = DEFAULT_MEMORY_SPACE_ID) -> str:
        if tier not in {"raw", "lesson", "global"}:
            raise ValueError(f"Invalid memory tier: {tier}")
        item_id = str(record.get("id") or record.get("lesson_id") or uuid.uuid4())
        created_at = str(record.get("timestamp_utc") or record.get("created_at") or record.get("promoted_at") or _utc_now())
        symbol = record.get("symbol") or record.get("coin") or record.get("ticker")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_items(id, memory_space_id, tier, symbol, trade_date, status, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    memory_space_id,
                    tier,
                    str(symbol) if symbol else None,
                    str(record.get("trade_date") or "") or None,
                    str(record.get("status") or "") or None,
                    _json_dumps(record),
                    created_at,
                ),
            )
        return item_id

    def load_memory(self, tier: str, memory_space_id: str = DEFAULT_MEMORY_SPACE_ID, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        sql = "SELECT payload_json FROM memory_items WHERE memory_space_id = ? AND tier = ? ORDER BY created_at ASC"
        params: List[Any] = [memory_space_id, tier]
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_json_loads(row["payload_json"], {}) for row in rows]

    def load_account(self, user_id: str, memory_space_id: str, default: Dict[str, Any]) -> Dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT account_json FROM paper_accounts WHERE user_id = ? AND memory_space_id = ?",
                (user_id, memory_space_id),
            ).fetchone()
        return _json_loads(row["account_json"], default) if row else default

    def save_account(self, user_id: str, memory_space_id: str, account: Dict[str, Any]) -> None:
        now = _utc_now()
        self.ensure_user(user_id)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO paper_accounts(user_id, memory_space_id, account_json, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, memory_space_id) DO UPDATE SET account_json=excluded.account_json, updated_at=excluded.updated_at
                """,
                (user_id, memory_space_id, _json_dumps(account), now),
            )

    def load_positions(self, user_id: str, memory_space_id: str) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM paper_positions
                WHERE user_id = ? AND memory_space_id = ? ORDER BY opened_at ASC
                """,
                (user_id, memory_space_id),
            ).fetchall()
        return [_json_loads(row["payload_json"], {}) for row in rows]

    def save_positions(self, user_id: str, memory_space_id: str, positions: Iterable[Dict[str, Any]]) -> None:
        now = _utc_now()
        rows = list(positions)
        with self.connect() as conn:
            conn.execute("DELETE FROM paper_positions WHERE user_id = ? AND memory_space_id = ?", (user_id, memory_space_id))
            for position in rows:
                conn.execute(
                    """
                    INSERT INTO paper_positions(id, user_id, memory_space_id, symbol, strategy, opened_at, payload_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(position.get("id") or uuid.uuid4()),
                        user_id,
                        memory_space_id,
                        str(position.get("symbol") or "") or None,
                        str(position.get("strategy") or "") or None,
                        str(position.get("opened_at") or "") or None,
                        _json_dumps(position),
                        now,
                    ),
                )

    def append_trade(self, user_id: str, memory_space_id: str, trade: Dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO paper_trades(user_id, memory_space_id, symbol, strategy, result, pnl_usdt, opened_at, closed_at, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    memory_space_id,
                    str(trade.get("symbol") or trade.get("coin") or "") or None,
                    str(trade.get("strategy") or "") or None,
                    str(trade.get("result") or "") or None,
                    float(trade.get("pnl_usdt") or trade.get("pnl_amount") or 0.0),
                    str(trade.get("opened_at") or "") or None,
                    str(trade.get("closed_at") or trade.get("timestamp_utc") or "") or None,
                    _json_dumps(trade),
                    str(trade.get("timestamp_utc") or _utc_now()),
                ),
            )
        self.append_memory("raw", trade, memory_space_id=memory_space_id)

    def load_trades(self, user_id: str, memory_space_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        sql = """
            SELECT payload_json FROM paper_trades
            WHERE user_id = ? AND memory_space_id = ? ORDER BY closed_at DESC, id DESC
        """
        params: List[Any] = [user_id, memory_space_id]
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_json_loads(row["payload_json"], {}) for row in rows]

    def load_candidates(self, user_id: str, memory_space_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM scan_candidates
                WHERE user_id = ? AND memory_space_id = ? ORDER BY scanned_at DESC, id DESC LIMIT ?
                """,
                (user_id, memory_space_id, int(limit)),
            ).fetchall()
        return [_json_loads(row["payload_json"], {}) for row in rows]

    def append_candidate(self, user_id: str, memory_space_id: str, candidate: Dict[str, Any]) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO scan_candidates(user_id, memory_space_id, symbol, strategy, scanned_at, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    memory_space_id,
                    str(candidate.get("symbol") or "") or None,
                    str(candidate.get("strategy") or "") or None,
                    str(candidate.get("scanned_at") or now),
                    _json_dumps(candidate),
                    now,
                ),
            )

    def clear_candidates(self, user_id: str, memory_space_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM scan_candidates WHERE user_id = ? AND memory_space_id = ?",
                (user_id, memory_space_id),
            ).fetchone()
            conn.execute("DELETE FROM scan_candidates WHERE user_id = ? AND memory_space_id = ?", (user_id, memory_space_id))
        return int(row["count"] if row else 0)

    def load_approvals(self, user_id: str, memory_space_id: str) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM pending_approvals
                WHERE user_id = ? AND memory_space_id = ? ORDER BY created_at ASC
                """,
                (user_id, memory_space_id),
            ).fetchall()
        return [_json_loads(row["payload_json"], {}) for row in rows]

    def save_approvals(self, user_id: str, memory_space_id: str, approvals: List[Dict[str, Any]]) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute("DELETE FROM pending_approvals WHERE user_id = ? AND memory_space_id = ?", (user_id, memory_space_id))
            for approval in approvals:
                approval_id = str(approval.get("id") or uuid.uuid4())
                signal = approval.get("signal") or {}
                conn.execute(
                    """
                    INSERT INTO pending_approvals(id, user_id, memory_space_id, symbol, status, created_at, payload_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        approval_id,
                        user_id,
                        memory_space_id,
                        str(signal.get("symbol") or approval.get("symbol") or "") or None,
                        str(approval.get("status") or "pending"),
                        str(approval.get("created_at") or now),
                        _json_dumps(approval),
                        now,
                    ),
                )

    def load_processed_signal_keys(self, user_id: str, memory_space_id: str, cutoff_iso: str) -> Dict[str, str]:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM processed_signal_keys WHERE user_id = ? AND memory_space_id = ? AND processed_at < ?",
                (user_id, memory_space_id, cutoff_iso),
            )
            rows = conn.execute(
                """
                SELECT signal_key, processed_at FROM processed_signal_keys
                WHERE user_id = ? AND memory_space_id = ? AND processed_at >= ?
                """,
                (user_id, memory_space_id, cutoff_iso),
            ).fetchall()
        return {str(row["signal_key"]): str(row["processed_at"]) for row in rows}

    def save_processed_signal_keys(self, user_id: str, memory_space_id: str, cache: Dict[str, str]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM processed_signal_keys WHERE user_id = ? AND memory_space_id = ?", (user_id, memory_space_id))
            for key, processed_at in cache.items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO processed_signal_keys(user_id, memory_space_id, signal_key, processed_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, memory_space_id, key, processed_at),
                )
