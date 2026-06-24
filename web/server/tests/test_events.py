import asyncio
import json
from datetime import datetime

import pytest

from web.server import storage
from web.server.events import EventType, emit, make_event
from web.server.runner import _NODE_STATE_KEY

EXPECTED_EVENT_TYPES = {
    "run_started",
    "run_failed",
    "run_finished",
    "analyst_started",
    "analyst_thinking",
    "analyst_completed",
    "tool_call",
    "tool_result",
    "tool_call_warning",
    "debate_message",
    "risk_message",
    "decision",
    "price_update",
    "server_notice",
}

EXPECTED_NODE_STATE_KEYS = {
    "Market Analyst",
    "Sentiment Analyst",
    "News Analyst",
    "Fundamentals Analyst",
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager",
    "Trader",
    "Aggressive Analyst",
    "Conservative Analyst",
    "Neutral Analyst",
    "Portfolio Manager",
}

EXPECTED_NODE_STATE_VALUES = {
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_debate_state.bull_history",
    "investment_debate_state.bear_history",
    "investment_plan",
    "trader_investment_plan",
    "risk_debate_state.aggressive_history",
    "risk_debate_state.conservative_history",
    "risk_debate_state.neutral_history",
    "final_trade_decision",
}


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


def test_event_type_enum_values_match_emissions():
    actual_values = {m.value for m in EventType}
    missing = EXPECTED_EVENT_TYPES - actual_values
    extra = actual_values - EXPECTED_EVENT_TYPES
    assert not missing, f"missing event type values: {missing}"
    assert not extra, f"unexpected event type values: {extra}"


def test_event_type_enum_dead_members_removed():
    dead = {"RUN_QUEUED", "RUN_DONE", "RUN_CANCELLED", "ANALYST_MESSAGE",
            "ANALYST_TOOL_CALL", "ANALYST_TOOL_RESULT", "STAGE_COMPLETED",
            "LLM_CALL", "TOKEN_USAGE"}
    actual = {m.name for m in EventType}
    remaining = dead & actual
    assert not remaining, f"dead event types still present: {remaining}"


def test_node_state_key_keys_match_graph_nodes():
    actual_keys = set(_NODE_STATE_KEY.keys())
    missing = EXPECTED_NODE_STATE_KEYS - actual_keys
    extra = actual_keys - EXPECTED_NODE_STATE_KEYS
    assert not missing, f"missing node keys: {missing}"
    assert not extra, f"unexpected node keys: {extra}"


def test_node_state_key_values_match_state_fields():
    actual_values = set(_NODE_STATE_KEY.values())
    missing = EXPECTED_NODE_STATE_VALUES - actual_values
    extra = actual_values - EXPECTED_NODE_STATE_VALUES
    assert not missing, f"missing state values: {missing}"
    assert not extra, f"unexpected state values: {extra}"


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
