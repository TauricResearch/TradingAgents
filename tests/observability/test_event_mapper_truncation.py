"""Tests for make_pm_decision event-mapper truncation whitelist (PR-B1.2)."""
import json

from agent_os.backend.services.event_mapper import EventMapper


def _make_chain_end_event(node_name: str, output_text: str) -> dict:
    """Build a minimal on_chain_end event for a LangGraph node."""
    return {
        "event": "on_chain_end",
        "run_id": "test-run-id",
        "name": node_name,
        "metadata": {"langgraph_node": node_name},
        "parent_ids": ["parent-run-id"],  # length 1 → node event (not root)
        "data": {"output": output_text},
        "tags": [],
    }


def test_pm_decision_result_not_truncated():
    """A make_pm_decision on_chain_end event must preserve full payload in 'response'."""
    long_payload = json.dumps({"buys": [{"ticker": "ET"}] * 50})
    assert len(long_payload) > 500

    mapper = EventMapper()
    mapper.register_run("exec_key", "test-identifier")

    event = _make_chain_end_event("make_pm_decision", long_payload)
    mapped = mapper.map_event("exec_key", event)

    assert mapped is not None
    assert mapped["response"] == long_payload, (
        f"PM decision response was truncated; got {len(mapped['response'])} chars, "
        f"expected {len(long_payload)}"
    )


def test_other_node_result_still_truncated():
    """Non-PM node results still respect _MAX_CONTENT_LEN to keep events small."""
    long_payload = "x" * 1000
    mapper = EventMapper()
    mapper.register_run("exec_key", "test-identifier")

    event = _make_chain_end_event("market_analyst", long_payload)
    mapped = mapper.map_event("exec_key", event)

    assert mapped is not None
    assert len(mapped["response"]) <= 350, (
        f"Expected truncated response (<= 350 chars), got {len(mapped['response'])}"
    )
