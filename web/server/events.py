"""Domain events: persist to disk + broadcast to WS subscribers."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Set

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


async def _broadcast(event: Dict[str, Any]) -> None:
    """Best-effort fanout to all WS subscribers (run-specific + global)."""
    rid = event.get("run_id")
    targets: List[WebSocket] = []
    if rid and rid in _subscribers:
        targets.extend(_subscribers[rid])
    targets.extend(_subscribers.get("*", []))
    for ws in targets:
        try:
            await ws.send_json(event)
        except Exception as exc:  # noqa: BLE001
            log.warning("WS broadcast failed: %s", exc)


def emit(run_id: str, type_: EventType, data: Dict[str, Any]) -> None:
    """Persist + broadcast a domain event. Safe to call from sync code."""
    event = make_event(run_id, type_, data)
    try:
        storage.append_run_event(run_id, event)
    except KeyError:
        log.warning("emit() called for unknown run_id=%s; dropping", run_id)
        return
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_broadcast(event))


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