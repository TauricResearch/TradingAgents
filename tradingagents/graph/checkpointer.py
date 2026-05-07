"""LangGraph checkpoint helpers for crash-recovery resume.

Each ticker gets its own SQLite database under ``<data_cache_dir>/checkpoints/``.
Thread IDs are deterministic SHA-256 hashes of ``TICKER:trade_date`` so that
a resumed run reconnects to the same checkpoint automatically.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from langgraph.checkpoint.sqlite import SqliteSaver

if TYPE_CHECKING:
    pass


def thread_id(ticker: str, trade_date: str) -> str:
    """Deterministic thread ID from ticker + trade_date.

    Returns the first 16 hex characters of SHA-256(``TICKER:trade_date``).
    """
    key = f"{ticker.upper()}:{trade_date}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _db_path(data_cache_dir: str, ticker: str) -> Path:
    """Return the per-ticker SQLite checkpoint DB path, creating parent dirs."""
    path = Path(data_cache_dir) / "checkpoints" / f"{ticker.upper()}.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def get_checkpointer(data_cache_dir: str, ticker: str) -> Generator[SqliteSaver, None, None]:
    """Context manager yielding a SqliteSaver backed by a per-ticker SQLite DB."""
    db = _db_path(data_cache_dir, ticker)
    conn = sqlite3.connect(str(db))
    try:
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()


def has_checkpoint(data_cache_dir: str, ticker: str, trade_date: str) -> bool:
    """Check whether a checkpoint exists for the given ticker and trade_date."""
    db = _db_path(data_cache_dir, ticker)
    if not db.exists():
        return False
    tid = thread_id(ticker, trade_date)
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.execute(
            "SELECT 1 FROM checkpoints WHERE thread_id = ? LIMIT 1",
            (tid,),
        )
        return cur.fetchone() is not None
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return False
    finally:
        conn.close()


def checkpoint_step(data_cache_dir: str, ticker: str, trade_date: str) -> int | None:
    """Return the latest checkpoint step number, or None if no checkpoint exists."""
    db = _db_path(data_cache_dir, ticker)
    if not db.exists():
        return None
    tid = thread_id(ticker, trade_date)
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.execute(
            "SELECT MAX(CAST(checkpoint_id AS INTEGER)) FROM checkpoints WHERE thread_id = ?",
            (tid,),
        )
        row = cur.fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def clear_checkpoint(data_cache_dir: str, ticker: str, trade_date: str) -> None:
    """Delete all checkpoint rows for the given thread_id."""
    db = _db_path(data_cache_dir, ticker)
    if not db.exists():
        return
    tid = thread_id(ticker, trade_date)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (tid,))
        conn.execute("DELETE FROM writes WHERE thread_id = ?", (tid,))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def clear_all_checkpoints(data_cache_dir: str) -> int:
    """Remove all checkpoint .db files. Returns the number of files removed."""
    checkpoint_dir = Path(data_cache_dir) / "checkpoints"
    if not checkpoint_dir.exists():
        return 0
    count = 0
    for db_file in checkpoint_dir.glob("*.db"):
        db_file.unlink()
        count += 1
    return count
