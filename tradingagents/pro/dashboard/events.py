"""Server-sent-event plumbing for the dashboard (live transport).

The trading loop runs in a plain worker thread; uvicorn runs an asyncio
loop. ``EventBroadcaster.publish`` is the thread-safe seam: it stamps an
id, appends to a replay ring, and hands fan-out to the loop via
``call_soon_threadsafe``. Each SSE client owns a bounded queue —
a stalled browser drops its own oldest events and can catch up from the
ring via ``Last-Event-ID``; it can never grow server memory or stall
the publisher.

In-process by design: the deployment runs a single uvicorn worker (see
deploy/Dockerfile.pro). Multiple workers would silently split the stream.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import threading
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass

from tradingagents.contracts import utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    id: int
    type: str
    data: str  # pre-serialized JSON

    def frame(self) -> str:
        return f"id: {self.id}\nevent: {self.type}\ndata: {self.data}\n\n"


KEEPALIVE_SECONDS = 15.0
# streams self-terminate after this long; clients reconnect with
# Last-Event-ID (see subscribe docstring — zombie streams exhaust Cloud
# Run's request concurrency)
STREAM_MAX_LIFETIME_SECONDS = 15 * 60.0


class EventBroadcaster:
    def __init__(self, replay: int = 256, queue_size: int = 512):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: dict[int, asyncio.Queue[Event]] = {}
        self._ring: deque[Event] = deque(maxlen=replay)
        self._seq = itertools.count(1)
        self._sub_ids = itertools.count(1)
        self._lock = threading.Lock()
        self._queue_size = queue_size

    # --- lifecycle (called from the app's lifespan) -----------------------------

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def ensure_loop(self) -> None:
        """Late binding for apps whose lifespan never ran (bare TestClient)."""
        if self._loop is None:
            self.bind_loop(asyncio.get_running_loop())

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    # --- publishing (any thread) -------------------------------------------------

    def publish(self, type_: str, data: dict) -> Event:
        payload = dict(data)
        payload.setdefault("time", utc_now().isoformat())
        with self._lock:
            event = Event(id=next(self._seq), type=type_,
                          data=json.dumps(payload, default=str))
            self._ring.append(event)
            loop = self._loop
        if loop is not None:
            if self._on_loop(loop):
                self._fanout(event)
            else:
                loop.call_soon_threadsafe(self._fanout, event)
        # loop not bound yet (before startup): ring keeps it for replay
        return event

    @staticmethod
    def _on_loop(loop: asyncio.AbstractEventLoop) -> bool:
        try:
            return asyncio.get_running_loop() is loop
        except RuntimeError:
            return False

    def _fanout(self, event: Event) -> None:
        with self._lock:
            queues = list(self._subscribers.values())
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:  # drop-oldest so a stalled client only hurts itself
                    queue.get_nowait()
                    queue.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    # --- subscribing (loop thread only) -------------------------------------------

    async def subscribe(self, last_event_id: int | None = None) -> AsyncIterator[str]:
        """Yields SSE frames (or keepalive comments) until the lifetime cap;
        caller cancels earlier. The cap matters on Cloud Run: every open
        stream counts against the instance's request-concurrency limit, and
        zombie streams from abandoned tabs accumulated until the load
        balancer started shedding requests with 429s (observed live —
        including a Cancel click). Healthy clients reconnect immediately
        with Last-Event-ID and the ring replays anything missed."""
        import time as _time

        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._queue_size)
        with self._lock:
            sub_id = next(self._sub_ids)
            self._subscribers[sub_id] = queue
            backlog = [e for e in self._ring
                       if last_event_id is not None and e.id > last_event_id]
        # A publish can land in the ring before registration while its
        # fan-out (call_soon_threadsafe) fires after — the event would
        # arrive via both paths. Monotonic id filtering dedupes.
        last_sent = last_event_id or 0
        deadline = _time.monotonic() + STREAM_MAX_LIFETIME_SECONDS
        try:
            for event in backlog:
                yield event.frame()
                last_sent = event.id
            while _time.monotonic() < deadline:
                try:
                    event = await asyncio.wait_for(queue.get(),
                                                   timeout=KEEPALIVE_SECONDS)
                    if event.id <= last_sent:
                        continue
                    yield event.frame()
                    last_sent = event.id
                except asyncio.TimeoutError:
                    # a real event, not a comment: EventSource cannot see
                    # comments, and the client needs heartbeats to keep its
                    # freshness indicator honest while nothing is happening
                    yield 'event: heartbeat\ndata: {}\n\n'
        finally:
            with self._lock:
                self._subscribers.pop(sub_id, None)


class BroadcastAlertSink:
    """AlertManager sink that mirrors every alert onto the SSE stream."""

    def __init__(self, broadcaster: EventBroadcaster):
        self.broadcaster = broadcaster

    def deliver(self, alert) -> None:
        self.broadcaster.publish("alert", alert.as_dict())
