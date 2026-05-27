"""Macro releases adapter — FRED releases (primary) + TradingEconomics calendar (secondary).

Open question O5 in the spec: default to FRED-primary; TE is skipped
unless TRADINGECONOMICS_KEY is set.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone

import redis.asyncio as aioredis
import requests

from tradingagents.sensing.adapters.base import EnvelopeWriter
from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


log = logging.getLogger(__name__)
NAME = "macro"
POLL_INTERVAL = 30 * 60


class MacroAdapter:
    name = NAME

    def __init__(self, *, staging_root: str, stream: str) -> None:
        self._staging = staging_root
        self._stream = stream

    async def _poll_fred(self, redis, conn, writer) -> int:
        key = os.environ.get("FRED_API_KEY")
        if not key:
            return 0
        try:
            r = requests.get(
                "https://api.stlouisfed.org/fred/releases",
                params={"api_key": key, "file_type": "json", "limit": 100,
                        "order_by": "release_id", "sort_order": "desc"},
                timeout=20,
            )
            r.raise_for_status(); data = r.json()
        except Exception as e:
            log.warning("FRED poll failed: %s", e); return 0
        cs = CursorStore(conn)
        last_id = int(cs.get(NAME) or "0")
        emitted = 0
        new_max = last_id
        for rel in data.get("releases", []):
            rid = int(rel.get("id", 0))
            if rid <= last_id:
                continue
            env = Envelope(
                source=NAME,
                ingested_ts=datetime.now(timezone.utc).isoformat(),
                external_id=f"fred:{rid}",
                text=rel.get("name", ""),
                source_tags={"provider": "fred", "release_id": rid,
                             "link": rel.get("link", "")},
                raw_path="",
            )
            await writer.write(env, raw_payload=rel, cursor=str(rid))
            emitted += 1
            new_max = max(new_max, rid)
        return emitted

    async def poll_once(self, *, redis: aioredis.Redis, conn: sqlite3.Connection) -> int:
        writer = EnvelopeWriter(source=NAME, redis=redis, conn=conn,
                                 stream=self._stream, staging_root=self._staging)
        n = await self._poll_fred(redis, conn, writer)
        # TE is intentionally a no-op until TRADINGECONOMICS_KEY ships.
        return n

    async def stream(self, *, redis, conn) -> None:
        backoff = 1
        while True:
            try:
                await self.poll_once(redis=redis, conn=conn); backoff = 1
            except Exception:
                log.exception("macro iteration crashed"); backoff = min(backoff * 2, 60)
            await asyncio.sleep(POLL_INTERVAL if backoff == 1 else backoff)


def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.sensing.redis_client import make_redis

    if not C["sensing_adapters_enabled"].get(NAME, True):
        log.info("%s disabled; exiting 0", NAME); return
    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])
    staging = os.path.join(C["iic_data_dir"], "events", "staging")
    a = MacroAdapter(staging_root=staging, stream=C["sensing_ingest_stream"])
    asyncio.run(a.stream(redis=redis, conn=conn))


if __name__ == "__main__":
    _main()
