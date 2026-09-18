import hashlib
import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

class MarketDataCache:
    """Persistent SQLite-backed cache with TTL for shared market data across jobs.

    Prevents redundant external API calls (Yahoo Finance, Alpha Vantage, FRED, Polymarket)
    when multiple concurrent or successive jobs analyze the same ticker or benchmark.
    """
    def __init__(self, db_path: Path = settings.CACHE_DIR / "market_data_cache.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                cache_key TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                data TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache_entries(expires_at);")

    def _make_key(self, category: str, params: dict[str, Any]) -> str:
        param_str = json.dumps(params, sort_keys=True, default=str)
        hashed = hashlib.sha256(param_str.encode("utf-8")).hexdigest()[:24]
        return f"{category}:{hashed}"

    def get(self, category: str, params: dict[str, Any]) -> Any | None:
        key = self._make_key(category, params)
        now_ts = int(time.time())
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT data, expires_at FROM cache_entries WHERE cache_key = ?", (key,)
                ).fetchone()
                if not row:
                    return None
                if row["expires_at"] < now_ts:
                    # Expired
                    conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (key,))
                    conn.commit()
                    return None
                return json.loads(row["data"])
        except Exception as e:
            logger.warning(f"Cache lookup failed for {key}: {e}")
            return None

    def set(self, category: str, params: dict[str, Any], data: Any, ttl_seconds: int | None = None):
        key = self._make_key(category, params)
        if ttl_seconds is None:
            ttl_seconds = settings.CACHE_TTL_HOURS * 3600
        expires_at = int(time.time()) + ttl_seconds
        created_at = datetime.utcnow().isoformat() + "Z"
        data_json = json.dumps(data, ensure_ascii=False)
        try:
            with self._get_conn() as conn:
                conn.execute("""
                INSERT OR REPLACE INTO cache_entries (cache_key, category, data, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """, (key, category, data_json, expires_at, created_at))
                conn.commit()
        except Exception as e:
            logger.warning(f"Cache write failed for {key}: {e}")

    def cleanup_expired(self) -> int:
        now_ts = int(time.time())
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM cache_entries WHERE expires_at < ?", (now_ts,))
            conn.commit()
            return cursor.rowcount

market_cache = MarketDataCache()
