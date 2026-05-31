"""GDELT 2.0 doc API adapter — 15-min poll."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone

import redis.asyncio as aioredis
import requests

from tradingagents.sensing.adapters.base import EnvelopeWriter
from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


log = logging.getLogger(__name__)
NAME = "gdelt"
POLL_INTERVAL = 15 * 60


class GdeltAdapter:
    name = NAME

    def __init__(self, *, query: str, staging_root: str, stream: str) -> None:
        self._query = query
        self._staging = staging_root
        self._stream = stream

    async def poll_once(self, *, redis: aioredis.Redis, conn: sqlite3.Connection) -> int:
        cs = CursorStore(conn)
        last_seen = cs.get(NAME) or ""
        try:
            r = requests.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={
                    "query": self._query,
                    "mode": "ArtList",
                    "format": "json",
                    "maxrecords": 250,
                    # DateDesc (newest-first): a news SENSOR must track the
                    # freshest articles. DateAsc returns the OLDEST 250 of the
                    # rolling window, so once the cursor passes them every later
                    # poll re-returns the same old set and emits 0 — gdelt would
                    # go silent after its first poll.
                    "sort": "DateDesc",
                },
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.warning("gdelt poll failed: %s", e); return 0

        writer = EnvelopeWriter(source=NAME, redis=redis, conn=conn,
                                 stream=self._stream, staging_root=self._staging)
        emitted = 0
        new_cursor = last_seen
        for art in data.get("articles", []):
            seen = art.get("seendate", "")
            if last_seen and seen <= last_seen:
                continue
            url = art.get("url", "")
            ext_id = f"gdelt:{url}"
            env = Envelope(
                source=NAME,
                ingested_ts=datetime.now(timezone.utc).isoformat(),
                external_id=ext_id,
                text=art.get("title", ""),
                source_tags={"domain": art.get("domain", ""), "url": url,
                             "seendate": seen},
                raw_path="",
            )
            await writer.write(env, raw_payload=art, cursor=seen)
            emitted += 1
            new_cursor = max(seen, new_cursor)
        return emitted

    async def stream(self, *, redis, conn) -> None:
        backoff = 1
        while True:
            try:
                await self.poll_once(redis=redis, conn=conn); backoff = 1
            except Exception:
                log.exception("gdelt iteration crashed"); backoff = min(backoff * 2, 60)
            await asyncio.sleep(POLL_INTERVAL if backoff == 1 else backoff)


def _main() -> None:
    import os
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.sensing.redis_client import make_redis

    if not C["sensing_adapters_enabled"].get(NAME, True):
        log.info("%s disabled; exiting 0", NAME); return
    # GDELT DOC 2.0 query rules: an OR-list MUST be wrapped in parentheses, and
    # keywords may not contain illegal chars like '&' (so "M&A" is rejected).
    # The override comes from GDELT_QUERY in .env (single-quote the whole value
    # there so the inner double-quotes survive .env parsing).
    query = os.environ.get(
        "GDELT_QUERY",
        '(earnings OR "federal reserve" OR "mergers and acquisitions")',
    )
    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])
    staging = os.path.join(C["iic_data_dir"], "events", "staging")
    a = GdeltAdapter(query=query, staging_root=staging,
                      stream=C["sensing_ingest_stream"])
    asyncio.run(a.stream(redis=redis, conn=conn))


if __name__ == "__main__":
    _main()
