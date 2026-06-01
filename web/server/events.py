"""WebSocket event protocol shared by backend emitter and frontend mirror."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from web.server import db


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"
    ANALYST_STARTED = "analyst_started"
    ANALYST_THINKING = "analyst_thinking"
    ANALYST_COMPLETED = "analyst_completed"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_CALL_WARNING = "tool_call_warning"
    DEBATE_MESSAGE = "debate_message"
    RISK_MESSAGE = "risk_message"
    DECISION = "decision"
    PRICE_UPDATE = "price_update"
    SERVER_NOTICE = "server_notice"


PROTOCOL_VERSION = 1


def make_event(type_: str, *, run_id: int, data: dict) -> dict:
    return {
        "v": PROTOCOL_VERSION,
        "type": type_,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": run_id,
        "data": data,
    }


_broadcast: Callable[[int, dict], None] = lambda run_id, evt: None


def set_broadcast(fn: Callable[[int, dict], None]) -> None:
    """Inject the WebSocket broadcast function. Called from app.py at startup."""
    global _broadcast
    _broadcast = fn


def emit(run_id: int, type_: str, data: dict) -> int:
    """Persist an event and broadcast it to live subscribers.

    Persistence failures are logged and broadcast still happens in-memory.
    Returns the event id on success, 0 on persistence failure.
    """
    evt = make_event(type_, run_id=run_id, data=data)
    event_id = 0
    try:
        event_id = db.append_event(run_id, type_, data)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("failed to persist event run=%s type=%s", run_id, type_)
    try:
        _broadcast(run_id, evt)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("broadcast failed run=%s type=%s", run_id, type_)
    return event_id


def wire_format(evt: dict) -> str:
    return json.dumps(evt, separators=(",", ":"))
