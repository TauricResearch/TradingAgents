"""LangGraph checkpoint support for resumable analysis runs.

Per-ticker SQLite databases so concurrent tickers don't contend.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from langgraph.checkpoint.sqlite import SqliteSaver

from tradingagents.dataflows.utils import safe_ticker_component


def _db_path(data_dir: str | Path, ticker: str) -> Path:
    """Return the SQLite checkpoint DB path for a ticker."""
    # Reject ticker values that would escape the checkpoints directory.
    safe = safe_ticker_component(ticker).upper()
    p = Path(data_dir) / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{safe}.db"


def thread_id(ticker: str, date: str) -> str:
    """Deterministic thread ID for a ticker+date pair."""
    return hashlib.sha256(f"{ticker.upper()}:{date}".encode()).hexdigest()[:16]


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


def has_checkpoint(data_dir: str | Path, ticker: str, date: str) -> bool:
    """Check whether a resumable checkpoint exists for ticker+date."""
    return checkpoint_step(data_dir, ticker, date) is not None


def checkpoint_step(data_dir: str | Path, ticker: str, date: str) -> int | None:
    """Return the step number of the latest checkpoint, or None if none exists."""
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return None
    tid = thread_id(ticker, date)
    with get_checkpointer(data_dir, ticker) as saver:
        config = {"configurable": {"thread_id": tid}}
        cp = saver.get_tuple(config)
        if cp is None:
            return None
        return cp.metadata.get("step")


def clear_all_checkpoints(data_dir: str | Path) -> int:
    """Remove all checkpoint DBs. Returns number of files deleted."""
    cp_dir = Path(data_dir) / "checkpoints"
    if not cp_dir.exists():
        return 0
    dbs = list(cp_dir.glob("*.db"))
    for db in dbs:
        db.unlink()
    return len(dbs)


def clear_checkpoint(data_dir: str | Path, ticker: str, date: str) -> None:
    """Remove checkpoint for a specific ticker+date by deleting the thread's rows."""
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return
    tid = thread_id(ticker, date)
    conn = sqlite3.connect(str(db))
    try:
        for table in ("writes", "checkpoints"):
            conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (tid,))
        conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def archive_checkpoint(
    data_dir: str | Path,
    ticker: str,
    date: str,
    archive_dir: Optional[str | Path] = None,
) -> Optional[Path]:
    """Copy the rows for one ``(ticker, date)`` thread to a standalone DB (T0.4).

    The active checkpoint store is per-ticker and holds rows for every
    date ever run against that ticker.  For audit we want each
    ``(ticker, date)`` pair extracted into its own standalone DB so that
    a regulator asking "show me your decision process on 2026-01-15"
    receives one self-contained file rather than a co-mingled per-ticker
    history.

    The destination path is ``{archive_dir}/checkpoints/{TICKER}/{date}.db``;
    ``archive_dir`` defaults to ``~/.tradingagents/audit``. An existing
    archive at the same path is overwritten — re-running the same
    ``(ticker, date)`` should produce an updated, not stacked, record.
    The active DB is left untouched; the caller is expected to invoke
    :func:`clear_checkpoint` afterwards.

    Returns the path of the written archive, or ``None`` if the source
    DB has no rows for this thread (e.g. checkpointing was disabled).
    """
    src_db = _db_path(data_dir, ticker)
    if not src_db.exists():
        return None

    tid = thread_id(ticker, date)

    # Quick existence check on the source so we don't materialise an empty
    # destination DB just to throw it away.
    src = sqlite3.connect(str(src_db))
    try:
        try:
            cur = src.execute(
                "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (tid,)
            )
            (n_rows,) = cur.fetchone()
        except sqlite3.OperationalError:
            # The active DB hasn't been initialised by SqliteSaver yet
            # — nothing to archive.
            return None
    finally:
        src.close()

    if n_rows == 0:
        return None

    # Resolve destination layout.
    archive_root = Path(
        archive_dir or Path.home() / ".tradingagents" / "audit"
    ).expanduser()
    safe = safe_ticker_component(ticker).upper()
    archive_subdir = archive_root / "checkpoints" / safe
    archive_subdir.mkdir(parents=True, exist_ok=True)
    dest_path = archive_subdir / f"{date}.db"
    # Overwrite, don't stack: an updated run for the same (ticker, date)
    # is more useful than a chain of partial archives.
    if dest_path.exists():
        dest_path.unlink()

    # Create destination schema via SqliteSaver.setup, then copy rows.
    src = sqlite3.connect(str(src_db))
    dest = sqlite3.connect(str(dest_path))
    try:
        saver = SqliteSaver(dest)
        saver.setup()

        for table in ("checkpoints", "writes"):
            try:
                cur = src.execute(
                    f"SELECT * FROM {table} WHERE thread_id = ?", (tid,)
                )
            except sqlite3.OperationalError:
                continue
            rows = cur.fetchall()
            if not rows:
                continue
            cols = [d[0] for d in cur.description]
            placeholders = ",".join("?" for _ in cols)
            dest.executemany(
                f"INSERT INTO {table} ({','.join(cols)}) "
                f"VALUES ({placeholders})",
                rows,
            )
        dest.commit()
    finally:
        src.close()
        dest.close()

    return dest_path
