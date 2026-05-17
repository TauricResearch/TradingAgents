"""
Redis pub-sub helpers for live run-progress streaming.

Channel convention: `run:<run_id>` — one channel per analysis run.
Producers (the LangChain callback handler during `/analyze`) publish
JSON-encoded events. Consumers (the SSE bridge in `/stream/{run_id}`)
subscribe and forward each event to the browser.

Treat this file as a python-temp-pro template — generic pub-sub helper,
no trading-specific knowledge.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import redis.asyncio as redis

from app.config import settings


logger = logging.getLogger(__name__)

# Sentinel value publishers send on the channel to signal "stream done."
# SSE consumers see this and close the connection cleanly. Picked an
# unlikely-to-collide marker string.
DONE_SENTINEL = "__run_done__"


def channel_for(run_id: str) -> str:
    return f"run:{run_id}"


# Fresh Redis client per call. Was briefly converted to a module-level
# singleton (TT-295 P1 code-review followup) but reverted because
# LangGraph dispatches callbacks across event loops — a singleton
# initialized at startup ends up attached to a different loop than the
# one publish_event runs on, surfacing as "got Future ... attached to a
# different loop" errors. The minor TCP+TLS overhead of per-call client
# creation is fine given Upstash's HTTP-like keepalive characteristics.
def _client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL)


async def publish_event(run_id: str, event: dict[str, Any]) -> None:
    """
    Publish one JSON event to `run:<run_id>`. No-op on Redis failure —
    the run itself shouldn't fail because pub-sub blipped. Sentry captures
    the underlying exception.
    """
    client = _client()
    try:
        payload = json.dumps(event, default=str)
        await client.publish(channel_for(run_id), payload)
    except Exception as e:
        logger.warning("pubsub publish failed for run %s: %s", run_id, e)
    finally:
        await client.aclose()


async def publish_done(run_id: str) -> None:
    """Mark the channel as finished so subscribers close cleanly."""
    client = _client()
    try:
        await client.publish(channel_for(run_id), DONE_SENTINEL)
    except Exception as e:
        logger.warning("pubsub publish-done failed for run %s: %s", run_id, e)
    finally:
        await client.aclose()


async def subscribe_events(run_id: str) -> AsyncIterator[str]:
    """
    Async iterator yielding raw message strings from `run:<run_id>` until
    a DONE_SENTINEL arrives. Caller is responsible for the connection
    lifetime — we expose a generator so it can be consumed inline by SSE.

    Yields the message data exactly as published (string). For JSON
    events, the consumer JSON-decodes after receiving.

    Subscribers always need a dedicated connection (Redis "subscribed
    mode" locks the connection to one subscription) — `_client()`
    already returns a fresh one per call.
    """
    client = _client()
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(channel_for(run_id))
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            if data == DONE_SENTINEL:
                return
            yield data
    finally:
        await pubsub.unsubscribe(channel_for(run_id))
        await pubsub.aclose()
        await client.aclose()
