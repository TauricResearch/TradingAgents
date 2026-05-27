"""Adapter contract + shared envelope-writing helper.

All adapters import EnvelopeWriter; the Protocol exists for documentation
and type-checking but is not strictly enforced at runtime.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import redis.asyncio as aioredis

from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


class IngestAdapter(Protocol):
    name: str  # "polygon_news", "telegram", ...

    async def stream(self, redis: aioredis.Redis, conn: sqlite3.Connection) -> None:
        """Long-lived. Reads from the source, writes envelopes to Redis,
        persists cursor after every successful batch. Defensively retry-internal."""


@dataclass
class EnvelopeWriter:
    """Writes raw payload to disk, XADDs envelope, advances cursor — atomically enough.

    The order is: write raw file → XADD envelope → set cursor. A crash between
    XADD and set-cursor results in the next adapter run re-fetching from the
    old cursor; the dedup pipeline tolerates the resulting re-deliveries.
    """
    source: str
    redis: aioredis.Redis
    conn: sqlite3.Connection
    stream: str
    staging_root: str

    def __post_init__(self) -> None:
        self._cursor = CursorStore(self.conn)
        Path(self.staging_root).mkdir(parents=True, exist_ok=True)

    def _write_raw(self, payload: dict) -> str:
        from datetime import datetime, timezone
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day_dir = Path(self.staging_root) / day
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"{uuid.uuid4().hex}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    async def write(
        self,
        env: Envelope,
        *,
        raw_payload: dict,
        cursor: str,
    ) -> None:
        raw_path = self._write_raw(raw_payload)
        # Envelope dataclass is frozen — rebuild with the real raw_path.
        env_with_path = Envelope(
            source=env.source, ingested_ts=env.ingested_ts,
            external_id=env.external_id, text=env.text,
            source_tags=env.source_tags, raw_path=raw_path,
        )
        await self.redis.xadd(self.stream, env_with_path.to_redis_fields())
        self._cursor.set(self.source, cursor)
