"""Tests for transport-level Anthropic prompt-cache injection.

``NormalizedChatAnthropic._get_request_payload`` marks the last system
block and the last eligible block of the final message with an ephemeral
``cache_control`` so the static prefix resent on every debate round /
tool-loop iteration becomes a cache read instead of fresh input tokens.
``TRADINGAGENTS_ANTHROPIC_CACHE=0`` disables the injection entirely.
"""

import pytest

from tradingagents.llm_clients.anthropic_client import (
    NormalizedChatAnthropic,
    _inject_cache_control,
)

EPHEMERAL = {"type": "ephemeral"}


def _count_markers(obj) -> int:
    if isinstance(obj, dict):
        return ("cache_control" in obj) + sum(
            _count_markers(v) for v in obj.values()
        )
    if isinstance(obj, list):
        return sum(_count_markers(item) for item in obj)
    return 0


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_ANTHROPIC_CACHE", raising=False)
    return NormalizedChatAnthropic(model="claude-haiku-4-5", api_key="x")


@pytest.mark.unit
class TestPayloadInjection:
    def test_string_system_and_human_get_marked(self, llm):
        payload = llm._get_request_payload([("system", "prefix"), ("human", "tail")])
        assert payload["system"] == [
            {"type": "text", "text": "prefix", "cache_control": EPHEMERAL}
        ]
        assert payload["messages"][-1]["content"] == [
            {"type": "text", "text": "tail", "cache_control": EPHEMERAL}
        ]

    def test_only_final_message_is_marked(self, llm):
        payload = llm._get_request_payload(
            [("system", "s"), ("human", "h1"), ("ai", "a1"), ("human", "h2")]
        )
        marked = [m for m in payload["messages"] if _count_markers(m)]
        assert len(marked) == 1
        assert marked[0] is payload["messages"][-1]

    def test_at_most_two_markers(self, llm):
        payload = llm._get_request_payload(
            [("system", "s"), ("human", "h1"), ("ai", "a1"), ("human", "h2")]
        )
        assert _count_markers(payload) == 2

    def test_no_system_message_still_marks_tail(self, llm):
        payload = llm._get_request_payload([("human", "tail")])
        assert "system" not in payload
        assert _count_markers(payload["messages"]) == 1

    def test_kill_switch_leaves_payload_untouched(self, llm, monkeypatch):
        baseline_input = [("system", "prefix"), ("human", "tail")]
        monkeypatch.setenv("TRADINGAGENTS_ANTHROPIC_CACHE", "0")
        payload = llm._get_request_payload(baseline_input)
        assert payload["system"] == "prefix"
        assert payload["messages"][-1]["content"] == "tail"
        assert _count_markers(payload) == 0


@pytest.mark.unit
class TestBlockSelection:
    def test_tool_result_tail_is_marked(self):
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "csv"},
                    ],
                }
            ]
        }
        _inject_cache_control(payload)
        assert payload["messages"][-1]["content"][-1]["cache_control"] == EPHEMERAL

    def test_ineligible_tail_blocks_are_skipped(self):
        payload = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "answer"},
                        {"type": "thinking", "thinking": "...", "signature": "sig"},
                    ],
                }
            ]
        }
        _inject_cache_control(payload)
        blocks = payload["messages"][-1]["content"]
        assert "cache_control" not in blocks[-1]  # thinking rejects the field
        assert blocks[0]["cache_control"] == EPHEMERAL

    def test_all_ineligible_blocks_is_a_no_op(self):
        payload = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [{"type": "thinking", "thinking": "...", "signature": "s"}],
                }
            ]
        }
        _inject_cache_control(payload)
        assert _count_markers(payload) == 0

    def test_existing_marker_is_not_overwritten(self):
        payload = {
            "system": [
                {"type": "text", "text": "s", "cache_control": {"type": "ephemeral", "ttl": "1h"}}
            ],
            "messages": [],
        }
        _inject_cache_control(payload)
        assert payload["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    def test_empty_payload_does_not_crash(self):
        payload = {"messages": []}
        _inject_cache_control(payload)
        assert _count_markers(payload) == 0
