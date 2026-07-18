"""LangGraph checkpoint support for resumable analysis runs.

Per-ticker SQLite databases so concurrent tickers don't contend.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import CheckpointTuple
from langgraph.checkpoint.sqlite import SqliteSaver

from tradingagents.dataflows.utils import safe_ticker_component


def _db_path(data_dir: str | Path, ticker: str) -> Path:
    """Return the SQLite checkpoint DB path for a ticker."""
    # Reject ticker values that would escape the checkpoints directory.
    safe = safe_ticker_component(ticker).upper()
    p = Path(data_dir) / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{safe}.db"


def thread_id(
    ticker: str,
    date: str,
    signature: str = "",
    *,
    run_id: str | None = None,
) -> str:
    """Deterministic thread ID for a ticker+date pair.

    ``signature`` folds in graph-shape-affecting run choices so a resume under a
    different graph can't reuse this checkpoint (#1089); omitting it keeps the
    legacy ID. Web runs additionally include their durable ``run_id`` namespace;
    omitting it preserves the exact legacy hash basis.
    """
    base = f"{ticker.upper()}:{date}"
    if signature:
        base = f"{base}:{signature}"
    if run_id is not None:
        if not run_id:
            raise ValueError("run_id must be non-empty when provided")
        base = f"web-v1:{run_id}:{base}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class CheckpointAccess:
    """Raw durable checkpoint frontier required for strict resume checks."""

    latest: CheckpointTuple | None
    parent: CheckpointTuple | None

    @property
    def pending_writes(self) -> list[tuple[str, str, Any]] | None:
        """Return the saver's pending-write object without normalization."""
        if self.latest is None:
            return None
        return self.latest.pending_writes


@contextmanager
def get_checkpointer(data_dir: str | Path, ticker: str) -> Generator[SqliteSaver, None, None]:
    """Context manager yielding a SqliteSaver backed by a per-ticker DB."""
    db = _db_path(data_dir, ticker)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()


def checkpoint_access(
    data_dir: str | Path,
    ticker: str,
    date: str,
    signature: str = "",
    *,
    run_id: str | None = None,
) -> CheckpointAccess:
    """Return the latest and its exact parent ``CheckpointTuple``.

    The parent's full config is supplied by LangGraph and must be reused as-is;
    reconstructing it from only a checkpoint ID would lose checkpoint namespace
    information.
    """
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return CheckpointAccess(latest=None, parent=None)
    tid = thread_id(ticker, date, signature, run_id=run_id)
    with get_checkpointer(data_dir, ticker) as saver:
        config = {"configurable": {"thread_id": tid}}
        latest = saver.get_tuple(config)
        parent = (
            saver.get_tuple(latest.parent_config)
            if latest is not None and latest.parent_config is not None
            else None
        )
        return CheckpointAccess(latest=latest, parent=parent)


def has_checkpoint(
    data_dir: str | Path,
    ticker: str,
    date: str,
    signature: str = "",
    *,
    run_id: str | None = None,
) -> bool:
    """Check whether a resumable checkpoint exists for ticker+date."""
    return checkpoint_step(data_dir, ticker, date, signature, run_id=run_id) is not None


def checkpoint_step(
    data_dir: str | Path,
    ticker: str,
    date: str,
    signature: str = "",
    *,
    run_id: str | None = None,
) -> int | None:
    """Return the step number of the latest checkpoint, or None if none exists."""
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return None
    tid = thread_id(ticker, date, signature, run_id=run_id)
    with get_checkpointer(data_dir, ticker) as saver:
        config = {"configurable": {"thread_id": tid}}
        checkpoint = saver.get_tuple(config)
        if checkpoint is None:
            return None
        return checkpoint.metadata.get("step")


def clear_all_checkpoints(data_dir: str | Path) -> int:
    """Remove all checkpoint DBs. Returns number of files deleted."""
    cp_dir = Path(data_dir) / "checkpoints"
    if not cp_dir.exists():
        return 0
    dbs = list(cp_dir.glob("*.db"))
    for db in dbs:
        db.unlink()
    return len(dbs)


def clear_checkpoint(
    data_dir: str | Path,
    ticker: str,
    date: str,
    signature: str = "",
    *,
    run_id: str | None = None,
) -> None:
    """Remove checkpoint for a specific ticker+date by deleting the thread's rows."""
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return
    tid = thread_id(ticker, date, signature, run_id=run_id)
    conn = sqlite3.connect(str(db))
    try:
        for table in ("writes", "checkpoints"):
            conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (tid,))
        conn.commit()
    except sqlite3.OperationalError:
        if run_id is not None:
            raise
    finally:
        conn.close()
