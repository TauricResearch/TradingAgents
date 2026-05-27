"""X (Twitter) sensing adapter — polled recent search.

Behind `sensing_adapters_enabled.x` config gate (default False) because
API access is in flux (spec R-F3-3). Tier-dependent: filtered stream
requires elevated; recent_search works on basic.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone

import redis.asyncio as aioredis
import tweepy

from tradingagents.sensing.adapters.base import EnvelopeWriter
from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


log = logging.getLogger(__name__)
NAME = "x"
POLL_INTERVAL = 60


class XAdapter:
    name = NAME

    def __init__(self, *, query: str, staging_root: str, stream: str) -> None:
        self._query = query
        self._staging = staging_root
        self._stream = stream

    async def poll_once(self, *, redis: aioredis.Redis, conn: sqlite3.Connection) -> int:
        token = os.environ.get("X_BEARER_TOKEN")
        if not token:
            log.warning("X_BEARER_TOKEN not set; skipping x poll"); return 0
        cs = CursorStore(conn)
        since_id = cs.get(NAME)
        try:
            client = tweepy.Client(bearer_token=token, wait_on_rate_limit=False)
            response = client.search_recent_tweets(
                query=self._query,
                since_id=int(since_id) if since_id else None,
                tweet_fields=["created_at", "author_id"],
                max_results=100,
            )
        except Exception as e:
            log.warning("x poll failed: %s", e); return 0
        tweets = response.data or []
        if not tweets:
            return 0
        writer = EnvelopeWriter(source=NAME, redis=redis, conn=conn,
                                 stream=self._stream, staging_root=self._staging)
        emitted = 0
        new_max = int(since_id) if since_id else 0
        for tw in tweets:
            env = Envelope(
                source=NAME,
                ingested_ts=datetime.now(timezone.utc).isoformat(),
                external_id=f"x:{tw.id}",
                text=getattr(tw, "text", ""),
                source_tags={"author_id": getattr(tw, "author_id", None)},
                raw_path="",
            )
            await writer.write(env, raw_payload={"id": tw.id,
                                                  "text": getattr(tw, "text", "")},
                               cursor=str(tw.id))
            new_max = max(new_max, int(tw.id))
            emitted += 1
        return emitted

    async def stream(self, *, redis, conn) -> None:
        backoff = 1
        while True:
            try:
                await self.poll_once(redis=redis, conn=conn); backoff = 1
            except Exception:
                log.exception("x iteration crashed"); backoff = min(backoff * 2, 120)
            await asyncio.sleep(POLL_INTERVAL if backoff == 1 else backoff)


def _main():
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.sensing.redis_client import make_redis

    if not C["sensing_adapters_enabled"].get(NAME, True):
        log.info("%s disabled; exiting 0", NAME); return None
    query = os.environ.get("X_QUERY", "$AAPL OR $TSLA OR $NVDA -is:retweet lang:en")
    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])
    staging = os.path.join(C["iic_data_dir"], "events", "staging")
    a = XAdapter(query=query, staging_root=staging,
                  stream=C["sensing_ingest_stream"])
    asyncio.run(a.stream(redis=redis, conn=conn))


if __name__ == "__main__":
    _main()
