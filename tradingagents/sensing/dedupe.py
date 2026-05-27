"""Two-stage dedupe pipeline.

Stage 1 catches re-deliveries / re-publishes via external_id + SHA-256 of the
normalized text. Cheap: one Redis SISMEMBER + one SQLite PK lookup.

Stage 2 (DedupeStage2) catches semantic duplicates across sources via embedding
cosine similarity over the last 24h.

Duplicates are NOT dropped — they are written to ``events`` with
``status='duplicate'`` and ``deduped_of=<original>`` so the exit gate
can score the 80% deduped criterion.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from .envelope import Envelope, normalize_for_fingerprint


def _fp(text: str) -> str:
    """SHA-256 hex of the normalized text. Used as the canonical fingerprint."""
    return hashlib.sha256(
        normalize_for_fingerprint(text).encode("utf-8")
    ).hexdigest()


class DedupeStage1:
    """Hash + external_id lookup via Redis hot-path then SQLite durable record."""

    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        redis: aioredis.Redis,
        fingerprint_ttl_hours: int,
    ) -> None:
        self._conn = conn
        self._redis = redis
        self._ttl_seconds = fingerprint_ttl_hours * 3600

    def _today_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d")

    def _sha_key(self) -> str:
        return f"fingerprints:sha:{self._today_utc()}"

    def _ext_key(self) -> str:
        return f"fingerprints:ext:{self._today_utc()}"

    async def check(self, env: Envelope) -> Optional[str]:
        """Return event_id of the original if this envelope is a duplicate, else None."""
        fp = _fp(env.text)

        # Hot path: Redis fingerprint sets for the last few days.
        # SISMEMBER is O(1); falling through to SQLite happens only on misses.
        if env.external_id:
            if await self._redis.sismember(self._ext_key(), env.external_id):
                row = self._conn.execute(
                    "SELECT event_id FROM event_fingerprints "
                    "WHERE fingerprint = ? AND kind = 'external_id'",
                    (env.external_id,),
                ).fetchone()
                if row:
                    return row["event_id"]
        if await self._redis.sismember(self._sha_key(), fp):
            row = self._conn.execute(
                "SELECT event_id FROM event_fingerprints "
                "WHERE fingerprint = ? AND kind = 'sha256'",
                (fp,),
            ).fetchone()
            if row:
                return row["event_id"]

        # Cold path: Redis missed (set expired or eviction). Check SQLite directly.
        if env.external_id:
            row = self._conn.execute(
                "SELECT event_id FROM event_fingerprints "
                "WHERE fingerprint = ? AND kind = 'external_id'",
                (env.external_id,),
            ).fetchone()
            if row:
                return row["event_id"]
        row = self._conn.execute(
            "SELECT event_id FROM event_fingerprints "
            "WHERE fingerprint = ? AND kind = 'sha256'",
            (fp,),
        ).fetchone()
        return row["event_id"] if row else None

    async def record(self, env: Envelope, *, event_id: str) -> None:
        """Persist the new event's fingerprints. Call ONLY on non-duplicates."""
        from tradingagents.persistence.store import insert_event_fingerprint
        fp = _fp(env.text)
        if env.external_id:
            insert_event_fingerprint(
                self._conn, fingerprint=env.external_id, kind="external_id",
                event_id=event_id, source=env.source,
            )
            await self._redis.sadd(self._ext_key(), env.external_id)
            await self._redis.expire(self._ext_key(), self._ttl_seconds)
        insert_event_fingerprint(
            self._conn, fingerprint=fp, kind="sha256",
            event_id=event_id, source=env.source,
        )
        await self._redis.sadd(self._sha_key(), fp)
        await self._redis.expire(self._sha_key(), self._ttl_seconds)
