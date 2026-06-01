from datetime import datetime, timezone
from web.server.events import EventType, emit, make_event, wire_format


def test_make_event_shape():
    e = make_event("analyst_thinking", run_id=42, data={"stage": "market", "message": "hi"})
    assert e["v"] == 1
    assert e["type"] == "analyst_thinking"
    assert e["run_id"] == 42
    assert e["data"] == {"stage": "market", "message": "hi"}
    assert isinstance(e["ts"], str)
    # ISO-8601
    datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))


def test_wire_format_is_json_serializable():
    import json
    e = make_event("decision", run_id=1, data={"action": "BUY", "target": 260.5})
    json.dumps(e)


def test_event_type_enum_has_required_keys():
    required = {
        "RUN_STARTED", "RUN_FINISHED", "RUN_FAILED",
        "ANALYST_STARTED", "ANALYST_THINKING", "ANALYST_COMPLETED",
        "TOOL_CALL", "TOOL_RESULT", "TOOL_CALL_WARNING",
        "DEBATE_MESSAGE", "RISK_MESSAGE", "DECISION",
        "PRICE_UPDATE", "SERVER_NOTICE",
    }
    actual = {m.name for m in EventType}
    missing = required - actual
    assert not missing, f"missing event types: {missing}"


def test_emit_persists_and_broadcasts(monkeypatch, temp_db):
    from web.server import db
    rid = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-06-01")
    seen = []
    monkeypatch.setattr("web.server.events._broadcast", lambda run_id, evt: seen.append(evt))

    eid = emit(rid, "analyst_thinking", {"stage": "market", "message": "hi"})
    assert eid > 0
    assert len(seen) == 1
    assert seen[0]["type"] == "analyst_thinking"

    events = db.events_for_run(rid)
    assert len(events) == 1
    import json
    assert json.loads(events[0].payload_json)["message"] == "hi"
