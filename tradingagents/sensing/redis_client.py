"""Async Redis factory + helpers shared by adapters and triage."""

from __future__ import annotations

import redis.asyncio as aioredis
from redis.exceptions import ResponseError


def make_redis(url: str) -> aioredis.Redis:
    """Single point that constructs the async Redis client.

    `decode_responses=True` so all reads return ``str`` — keeps Envelope
    serialization simple.
    """
    return aioredis.from_url(url, decode_responses=True)


async def ensure_consumer_group(
    r: aioredis.Redis, *, stream: str, group: str,
) -> None:
    """Idempotent XGROUP CREATE with MKSTREAM.

    Already-exists is the only acceptable error.
    """
    try:
        await r.xgroup_create(name=stream, groupname=group, id="0",
                              mkstream=True)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise
