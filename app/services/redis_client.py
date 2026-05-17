"""
TT-295: shared Redis client + subscriber factory.

Previously every publish / health-check / subscribe call did
`redis.from_url(...)` and closed the resulting client immediately. That
opens a fresh TCP + TLS + Upstash auth handshake per call — wasteful
for high-frequency paths like Railway's /ready probe (every ~30s) and
the per-agent publish_event calls during an analysis run.

`get_redis()` returns a process-wide singleton. Connection pooling
inside the client handles concurrency.

`make_subscriber()` returns a NEW client every call — pub-sub
subscribers must own a dedicated connection because subscribing puts
the connection in "subscribed mode" and can't be shared. Callers are
still responsible for closing the subscriber client via `.aclose()`.

Treat this file as a python-temp-pro template — generic Redis lifecycle
helper, no trading-specific knowledge.
"""

from __future__ import annotations

import redis.asyncio as redis

from app.config import settings


_singleton: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """
    Shared Redis client for publishers + health checks + anything that
    doesn't need a dedicated subscriber connection. Lazy-initialized on
    first call; reused for the lifetime of the process.
    """
    global _singleton
    if _singleton is None:
        _singleton = redis.from_url(settings.REDIS_URL)
    return _singleton


def make_subscriber() -> redis.Redis:
    """
    Fresh Redis client for pub-sub subscription. Each subscriber needs
    its own connection — Redis "subscribed mode" locks the connection
    to that single subscription. Caller owns the lifecycle (must
    .aclose() when done).
    """
    return redis.from_url(settings.REDIS_URL)


async def close_redis() -> None:
    """
    Close the shared singleton. Wire into FastAPI shutdown so the TCP
    socket gets cleanly closed on container stop.
    """
    global _singleton
    if _singleton is not None:
        await _singleton.aclose()
        _singleton = None
