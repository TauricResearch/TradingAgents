import asyncio
import json
from datetime import datetime, timezone

import pytest

from web.server.events import EventType, emit, make_event
from web.server import storage


def test_make_event_shape():
    e = make_event("42", "analyst_thinking", {"stage": "market", "message": "hi"})
    assert e["run_id"] == "42"
    assert e["type"] == "analyst_thinking"
    assert e["data"] == {"stage": "market", "message": "hi"}
    assert isinstance(e["ts"], str)
    assert isinstance(e["id"], str)
    # ISO-8601 with Z suffix
    datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))


def test_wire_format_is_json_serializable():
    e = make_event("1", "decision", {"action": "BUY", "target": 260.5})
    # The canonical event dict must round-trip through json.dumps unchanged
    # of shape (i.e. no datetime/set/bytes in the payload).
    json.dumps(e)


def test_event_type_enum_has_required_keys():
    required = {
        "RUN_QUEUED", "RUN_STARTED", "RUN_DONE", "RUN_FAILED", "RUN_CANCELLED",
        "ANALYST_STARTED", "ANALYST_THINKING", "ANALYST_MESSAGE",
        "ANALYST_TOOL_CALL", "ANALYST_TOOL_RESULT", "ANALYST_COMPLETED",
        "STAGE_COMPLETED", "LLM_CALL", "TOKEN_USAGE",
    }
    actual = {m.name for m in EventType}
    missing = required - actual
    assert not missing, f"missing event types: {missing}"


@pytest.mark.asyncio
async def test_emit_persists_and_broadcasts(monkeypatch, data_root):
    info = storage.create_run_dir("NVDA")
    rid = info["run_id"]
    seen = []

    async def fake_broadcast(event):
        seen.append(event)

    monkeypatch.setattr("web.server.events._broadcast", fake_broadcast)

    # The real emit() persists to disk via storage.append_run_event and then
    # schedules a broadcast task on the running loop. Yield once so the
    # scheduled task has a chance to run before we assert.
    emit(rid, "analyst_thinking", {"stage": "market", "message": "hi"})
    await asyncio.sleep(0.01)

    assert len(seen) == 1
    assert seen[0]["type"] == "analyst_thinking"
    assert seen[0]["data"]["message"] == "hi"

    events = storage.list_run_events(rid)
    assert len(events) == 1
    assert events[0]["data"]["message"] == "hi"
    assert events[0]["type"] == "analyst_thinking"
    assert events[0]["run_id"] == rid
