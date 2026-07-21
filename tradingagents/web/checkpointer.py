"""Async checkpoint support for web runs.

The repo's ``tradingagents.graph.checkpointer`` is sqlite3/sync-only; its
``SqliteSaver`` hard-raises ``NotImplementedError`` from the async Pregel
loop, so checkpoint-enabled web runs must compile with ``AsyncSqliteSaver``.
Thread IDs, step lookup, and clearing reuse the sync module verbatim so a
run started in the CLI can resume in the web UI and vice versa.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from tradingagents.graph.checkpointer import (  # noqa: F401  (re-exported parity API)
    _db_path,
    checkpoint_step,
    clear_checkpoint,
    thread_id,
)


@asynccontextmanager
async def open_async_checkpointer(data_dir: str | Path, ticker: str):
    """Async context manager yielding an AsyncSqliteSaver on the per-ticker DB."""
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    db = _db_path(data_dir, ticker)
    conn = await aiosqlite.connect(str(db))
    try:
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        yield saver
    finally:
        await conn.close()
