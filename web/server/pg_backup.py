"""PostgreSQL backup for persistent data across redeploys on Render.

Render's free tier provides a managed PostgreSQL instance (1 GB storage)
whose lifetime outlives any single web-service deployment. This module
stores a copy of every data-dir file in a simple key-value table so
data survives redeploys.

Write-through pattern:
  - Every file write via ``storage`` is synced to PostgreSQL immediately.
  - On cold start, all files are restored from PostgreSQL to the local
    data dir before the app serves requests.

Configured automatically when ``DATABASE_URL`` env var is present
(Render injects this for attached PostgreSQL services).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

TABLE = "tradingagents_data_backup"
_enabled = False
_conn_str: str = ""
_local_data_dir: Path | None = None


def is_enabled() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def _get_connection():
    import psycopg2  # type: ignore[import-untyped]

    return psycopg2.connect(_conn_str)


def _ensure_table() -> None:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    path TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
        conn.commit()
    finally:
        conn.close()


def init(data_dir: str | Path) -> None:
    """Initialize PostgreSQL backup.

    Called from app lifespan after ``storage.init_settings``.
    Registers the write hook and restores data from PG if available.
    """
    global _enabled, _conn_str, _local_data_dir

    if not is_enabled():
        _enabled = False
        return

    _conn_str = os.environ["DATABASE_URL"]
    _local_data_dir = Path(data_dir)
    _enabled = True

    from web.server import storage

    storage._write_hook = _sync_to_pg

    try:
        _ensure_table()
        _restore_from_pg()
    except Exception:
        log.exception("failed to init PostgreSQL backup")


def _restore_from_pg() -> None:
    """Download all rows from PostgreSQL to the local data dir."""
    if _local_data_dir is None:
        return
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT path, content FROM {TABLE}")
            rows = cur.fetchall()
        restored = 0
        for path_str, content_b64 in rows:
            local_path = _local_data_dir / path_str
            if local_path.exists():
                continue
            import base64

            content_bytes = base64.b64decode(content_b64.encode("ascii"))
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(content_bytes)
            restored += 1
        if restored:
            log.info("restored %d files from PostgreSQL", restored)
    finally:
        conn.close()


def _sync_to_pg(path: Path) -> None:
    """Write-through: upsert a file's content into PostgreSQL."""
    if not _enabled or not path.exists() or _local_data_dir is None:
        return
    try:
        rel = path.relative_to(_local_data_dir).as_posix()
    except ValueError:
        return
    try:
        import base64

        content_bytes = path.read_bytes()
        content_b64 = base64.b64encode(content_bytes).decode("ascii")
        conn = _get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {TABLE} (path, content, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (path)
                    DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
                    """,
                    (rel, content_b64),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        log.exception("failed to sync %s to PostgreSQL", path)
