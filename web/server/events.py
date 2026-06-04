"""Domain events: persist to disk + broadcast to WS subscribers."""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

from . import storage

log = logging.getLogger(__name__)


class EventType(str, Enum):
    """All 14 event types. String values are part of the WS protocol."""

    RUN_QUEUED = "run_queued"
    RUN_STARTED = "run_started"
    RUN_DONE = "run_done"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"
    ANALYST_STARTED = "analyst_started"
    ANALYST_THINKING = "analyst_thinking"
    ANALYST_MESSAGE = "analyst_message"
    ANALYST_TOOL_CALL = "analyst_tool_call"
    ANALYST_TOOL_RESULT = "analyst_tool_result"
    ANALYST_COMPLETED = "analyst_completed"
    STAGE_COMPLETED = "stage_completed"
    LLM_CALL = "llm_call"
    TOKEN_USAGE = "token_usage"


def make_event(run_id: str, type_: EventType, data: Dict[str, Any]) -> Dict[str, Any]:
    """Build the canonical event dict that goes on the wire + to disk."""
    return {
        "id": f"{run_id}:{datetime.now(timezone.utc).timestamp():.6f}",
        "run_id": run_id,
        "type": type_.value if isinstance(type_, EventType) else str(type_),
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data": data,
    }


_subscribers: Dict[str, Set[WebSocket]] = {}

# Reference to the main event loop, captured by the app lifespan.
# ``events.emit()`` is called from worker threads (graph nodes run
# inside ``loop.run_in_executor``); the broadcast coroutine must run on
# the main loop so WS clients receive live events. We use
# ``asyncio.run_coroutine_threadsafe`` for that. When unset (unit tests
# that call ``emit()`` directly from the main thread), ``emit()`` falls
# back to ``asyncio.get_running_loop()`` for backwards compatibility.
_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_lock = threading.Lock()


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Capture the main event loop reference. Called once from app lifespan.

    Required for live WS broadcast from worker threads: graph nodes run
    inside ``loop.run_in_executor`` and call ``events.emit()`` synchronously;
    without a captured loop reference, the broadcast can only be scheduled
    on the calling thread's loop, which doesn't exist in a worker thread
    and so the broadcast silently never happens (UI shows stale state
    until reconnect).
    """
    global _loop
    with _loop_lock:
        _loop = loop
    log.debug("events: captured event loop %s", loop)


def _get_event_loop() -> Optional[asyncio.AbstractEventLoop]:
    """Return the captured loop, or ``None`` if not set / closed."""
    if _loop is None:
        return None
    if _loop.is_closed():
        return None
    return _loop


def _subscriber_count(run_id: str) -> int:
    """Total number of WS subscribers (per-run + global). For debug logging."""
    return len(_subscribers.get(run_id, set())) + len(_subscribers.get("*", set()))


async def _broadcast(event: Dict[str, Any]) -> None:
    """Best-effort fanout to all WS subscribers (run-specific + global)."""
    rid = event.get("run_id")
    # Copy target list so subscribe/unsubscribe during the await doesn't
    # race with this iteration.
    targets: List[WebSocket] = []
    if rid and rid in _subscribers:
        targets.extend(_subscribers[rid])
    targets.extend(_subscribers.get("*", []))

    log.debug(
        "broadcast: rid=%s type=%s id=%s subscribers=%d",
        rid, event.get("type"), event.get("id"), len(targets),
    )

    for ws in targets:
        try:
            await ws.send_json(event)
        except Exception as exc:  # noqa: BLE001
            log.warning("WS broadcast failed: %s", exc)


def emit(run_id: str, type_: EventType, data: Dict[str, Any]) -> None:
    """Persist + broadcast a domain event. Safe to call from any thread.

    Persistence is always synchronous on the calling thread. Broadcast is
    scheduled on the main loop (captured via :func:`set_event_loop`) using
    ``asyncio.run_coroutine_threadsafe`` so WS clients receive live
    events even when ``emit()`` is called from a worker thread inside
    ``loop.run_in_executor``.

    When no loop has been captured (e.g. unit tests calling ``emit()``
    directly), falls back to ``asyncio.get_running_loop()`` on the
    calling thread — the legacy behaviour, kept so the original test in
    ``test_emit_persists_and_broadcasts`` still works.
    """
    event = make_event(run_id, type_, data)
    try:
        storage.append_run_event(run_id, event)
    except KeyError:
        log.warning("emit() called for unknown run_id=%s; dropping", run_id)
        return

    main_loop = _get_event_loop()
    if main_loop is not None:
        # Cross-thread path: schedule on the main loop.
        try:
            asyncio.run_coroutine_threadsafe(_broadcast(event), main_loop)
            log.debug(
                "emit: rid=%s type=%s id=%s scheduled (subscribers=%d)",
                run_id, event["type"], event["id"], _subscriber_count(run_id),
            )
            return
        except RuntimeError as exc:
            # Loop was closed between the check and the schedule.
            log.warning("emit: failed to schedule broadcast: %s", exc)
            return

    # Same-thread fallback: try the calling thread's loop.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        log.debug(
            "emit: rid=%s type=%s id=%s persisted (no loop available)",
            run_id, event["type"], event["id"],
        )
        return
    loop.create_task(_broadcast(event))
    log.debug(
        "emit: rid=%s type=%s id=%s scheduled same-thread (subscribers=%d)",
        run_id, event["type"], event["id"], _subscriber_count(run_id),
    )


def subscribe(run_id: str, ws: WebSocket) -> None:
    _subscribers.setdefault(run_id, set()).add(ws)


def unsubscribe(run_id: str, ws: WebSocket) -> None:
    if run_id in _subscribers:
        _subscribers[run_id].discard(ws)
        if not _subscribers[run_id]:
            del _subscribers[run_id]


def subscribe_global(ws: WebSocket) -> None:
    _subscribers.setdefault("*", set()).add(ws)


def unsubscribe_global(ws: WebSocket) -> None:
    if "*" in _subscribers:
        _subscribers["*"].discard(ws)
        if not _subscribers["*"]:
            del _subscribers["*"]


def reset_for_tests() -> None:
    """Reset module state (subscribers + captured loop). Test-only."""
    global _loop
    _subscribers.clear()
    with _loop_lock:
        _loop = None
