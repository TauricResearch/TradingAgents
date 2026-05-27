"""RSS adapter — feedparser per feed, 5-min interval, per-feed cursors.

Cursor format: JSON dict mapping feed_url → max published ISO timestamp.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import List

import feedparser
import redis.asyncio as aioredis

from tradingagents.sensing.adapters.base import EnvelopeWriter
from tradingagents.sensing.cursor import CursorStore
from tradingagents.sensing.envelope import Envelope


log = logging.getLogger(__name__)
NAME = "rss"
POLL_INTERVAL = 5 * 60


def _entry_ts(entry) -> str:
    if getattr(entry, "published_parsed", None):
        dt = datetime.fromtimestamp(time.mktime(entry.published_parsed),
                                     tz=timezone.utc)
        return dt.isoformat()
    return datetime.now(timezone.utc).isoformat()


class RssAdapter:
    name = NAME

    def __init__(self, *, feeds: List[str], staging_root: str, stream: str) -> None:
        self._feeds = list(feeds)
        self._staging = staging_root
        self._stream = stream

    def _load_cursor(self, conn) -> dict:
        cs = CursorStore(conn)
        raw = cs.get(NAME)
        return json.loads(raw) if raw else {}

    def _save_cursor(self, conn, d: dict) -> None:
        CursorStore(conn).set(NAME, json.dumps(d))

    async def poll_once(self, *, redis: aioredis.Redis, conn: sqlite3.Connection) -> int:
        cursors = self._load_cursor(conn)
        writer = EnvelopeWriter(source=NAME, redis=redis, conn=conn,
                                 stream=self._stream, staging_root=self._staging)
        emitted = 0
        for feed_url in self._feeds:
            try:
                feed = feedparser.parse(feed_url)
            except Exception as e:
                log.warning("rss parse failed for %s: %s", feed_url, e)
                continue
            last = cursors.get(feed_url, "")
            new_last = last
            for entry in feed.entries:
                ts = _entry_ts(entry)
                if last and ts <= last:
                    continue
                ext_id = f"rss:{getattr(entry, 'id', getattr(entry, 'link', ''))}"
                text = " ".join(filter(None, [
                    getattr(entry, "title", ""),
                    getattr(entry, "summary", ""),
                ]))
                env = Envelope(
                    source=NAME,
                    ingested_ts=datetime.now(timezone.utc).isoformat(),
                    external_id=ext_id, text=text,
                    source_tags={"feed": feed_url,
                                 "link": getattr(entry, "link", "")},
                    raw_path="",
                )
                # Per-entry cursor is the feed-level dict, JSON-encoded.
                cursors[feed_url] = ts
                await writer.write(
                    env,
                    raw_payload={
                        "title": getattr(entry, "title", ""),
                        "summary": getattr(entry, "summary", ""),
                        "link": getattr(entry, "link", ""),
                        "published_ts": ts,
                    },
                    cursor=json.dumps(cursors),
                )
                emitted += 1
                new_last = ts
            cursors[feed_url] = max(new_last, last) if last else new_last
        self._save_cursor(conn, cursors)
        return emitted

    async def stream(self, *, redis, conn) -> None:
        backoff = 1
        while True:
            try:
                await self.poll_once(redis=redis, conn=conn)
                backoff = 1
            except Exception:
                log.exception("rss stream iteration crashed")
                backoff = min(backoff * 2, 60)
            await asyncio.sleep(POLL_INTERVAL if backoff == 1 else backoff)


def _main() -> None:
    import os
    logging.basicConfig(level=logging.INFO)
    from tradingagents.default_config import DEFAULT_CONFIG as C
    from tradingagents.persistence.db import connect
    from tradingagents.sensing.redis_client import make_redis

    if not C["sensing_adapters_enabled"].get(NAME, True):
        log.info("%s disabled; exiting 0", NAME); return
    feeds = [f.strip() for f in os.environ.get("RSS_FEEDS", "").split(",") if f.strip()]
    if not feeds:
        log.warning("RSS_FEEDS env var not set; no feeds to poll")
    redis = make_redis(C["sensing_redis_url"])
    conn = connect(C["iic_db_path"])
    staging = os.path.join(C["iic_data_dir"], "events", "staging")
    a = RssAdapter(feeds=feeds, staging_root=staging,
                    stream=C["sensing_ingest_stream"])
    asyncio.run(a.stream(redis=redis, conn=conn))


if __name__ == "__main__":
    _main()
