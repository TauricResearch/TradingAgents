"""Tests for StreamingCallbackHandler.

The handler bridges LangChain per-step callbacks into the dashboard's
WsEvent protocol. We test against a captured broadcast list rather
than against the live WS queue.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from web.server.callbacks import StreamingCallbackHandler


def _make():
    events = []
    def broadcast(evt):
        events.append(evt)
    return StreamingCallbackHandler(run_id=42, broadcast=broadcast), events


@pytest.mark.unit
class TestOnChatModelStart:
    def test_emits_analyst_thinking_with_prompt_preview(self):
        handler, events = _make()
        handler.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[HumanMessage(content="What's the price of NVDA?")]],
        )
        assert len(events) == 1
        assert events[0]["type"] == "analyst_thinking"
        assert events[0]["run_id"] == 42
        assert events[0]["data"]["text_preview"] == "What's the price of NVDA?"

    def test_truncates_long_prompts_to_200_chars(self):
        handler, events = _make()
        long_msg = "x" * 1000
        handler.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[HumanMessage(content=long_msg)]],
        )
        assert len(events[0]["data"]["text_preview"]) == 200

    def test_handles_missing_human_message(self):
        handler, events = _make()
        handler.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[AIMessage(content="no user input here")]],
        )
        assert len(events) == 0


@pytest.mark.unit
class TestOnLlmEnd:
    def test_emits_analyst_thinking_for_text_response(self):
        handler, events = _make()
        gen = MagicMock()
        chat = MagicMock()
        chat.message = AIMessage(content="Some analysis text.")
        chat.message.tool_calls = []
        gen.__iter__ = lambda self: iter([chat])
        result = MagicMock()
        result.generations = [gen]
        handler.on_llm_end(result)
        assert any(e["data"].get("text_fragment") == "Some analysis text." for e in events)

    def test_skips_when_response_has_tool_calls(self):
        handler, events = _make()
        gen = MagicMock()
        chat = MagicMock()
        chat.message = AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "1"}])
        gen.__iter__ = lambda self: iter([chat])
        result = MagicMock()
        result.generations = [gen]
        handler.on_llm_end(result)
        assert events == []


@pytest.mark.unit
class TestOnTool:
    def test_on_tool_start_emits_tool_call(self):
        handler, events = _make()
        handler.on_tool_start({"name": "get_stock_data"}, '{"ticker": "NVDA"}')
        assert len(events) == 1
        assert events[0]["type"] == "tool_call"
        assert events[0]["data"]["tool"] == "get_stock_data"
        assert events[0]["data"]["args"] == '{"ticker": "NVDA"}'

    def test_on_tool_end_emits_tool_result_with_string_output(self):
        handler, events = _make()
        handler.on_tool_end("the price is 900")
        assert len(events) == 1
        assert events[0]["type"] == "tool_result"
        assert events[0]["data"]["summary"] == "the price is 900"

    def test_on_tool_end_emits_tool_result_with_ToolMessage(self):
        handler, events = _make()
        msg = ToolMessage(content="price=900", name="get_stock_data", tool_call_id="1")
        handler.on_tool_end(msg)
        assert events[0]["data"]["summary"] == "price=900"
        assert events[0]["data"]["tool"] == "get_stock_data"

    def test_on_tool_error_emits_tool_result_with_error(self):
        handler, events = _make()
        handler.on_tool_error(ValueError("bad arg"))
        assert len(events) == 1
        assert events[0]["data"]["error"] == "bad arg"
        assert events[0]["data"]["summary"] == "bad arg"


from web.server.callbacks import CaptureCallbackHandler  # noqa: E402


@pytest.mark.unit
class TestCaptureCallbackHandler:
    def test_captures_full_prompt_and_response(self):
        calls = []
        handler = CaptureCallbackHandler(run_id=42, ticker="NVDA", save_call=calls.append)

        from uuid import uuid4
        rid = uuid4()
        handler.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[HumanMessage(content="What's the price?")]],
            run_id=rid,
        )
        # Simulate on_llm_end with a proper LLMResult
        from unittest.mock import MagicMock
        gen = MagicMock()
        chat = MagicMock()
        chat.message = AIMessage(content="The price is 900.", tool_calls=[])
        gen.__iter__ = lambda self: iter([chat])
        result = MagicMock()
        result.generations = [gen]
        result.llm_output = {"model_name": "gpt-4", "token_usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}}

        handler.on_llm_end(result, run_id=rid)

        assert len(calls) == 1
        call = calls[0]
        assert call["run_id"] == 42
        assert call["ticker"] == "NVDA"
        assert "What's the price?" in call["prompt_text"]
        assert call["response_text"] == "The price is 900."
        assert call["total_tokens"] == 8
        assert call["input_tokens"] == 5
        assert call["output_tokens"] == 3

    def test_multiple_llm_calls_tracked_independently(self):
        calls = []
        handler = CaptureCallbackHandler(run_id=42, ticker="NVDA", save_call=calls.append)
        from uuid import uuid4
        rid1, rid2 = uuid4(), uuid4()

        handler.on_chat_model_start({"name": "ChatOpenAI"}, [[HumanMessage(content="first call")]], run_id=rid1)
        handler.on_chat_model_start({"name": "ChatOpenAI"}, [[HumanMessage(content="second call")]], run_id=rid2)
        gen = MagicMock()
        chat = MagicMock()
        chat.message = AIMessage(content="first response")
        gen.__iter__ = lambda self: iter([chat])
        r1 = MagicMock()
        r1.generations = [gen]
        r1.llm_output = {"token_usage": {"total_tokens": 1}}
        handler.on_llm_end(r1, run_id=rid1)

        chat2 = MagicMock()
        chat2.message = AIMessage(content="second response")
        gen2 = MagicMock()
        gen2.__iter__ = lambda self: iter([chat2])
        r2 = MagicMock()
        r2.generations = [gen2]
        r2.llm_output = {"token_usage": {"total_tokens": 2}}
        handler.on_llm_end(r2, run_id=rid2)

        assert len(calls) == 2
        assert calls[0]["response_text"] == "first response"
        assert calls[1]["response_text"] == "second response"

    def test_handles_tool_calls_in_response(self):
        calls = []
        handler = CaptureCallbackHandler(run_id=42, ticker="NVDA", save_call=calls.append)
        from uuid import uuid4
        rid = uuid4()
        handler.on_chat_model_start({"name": "ChatOpenAI"}, [[HumanMessage(content="check price")]], run_id=rid)
        gen = MagicMock()
        chat = MagicMock()
        chat.message = AIMessage(content="", tool_calls=[{"name": "get_price", "args": {}, "id": "call_1"}])
        gen.__iter__ = lambda self: iter([chat])
        r = MagicMock()
        r.generations = [gen]
        r.llm_output = {}
        handler.on_llm_end(r, run_id=rid)
        assert len(calls) == 1
        assert len(calls[0]["tool_calls"]) == 1
        assert calls[0]["tool_calls"][0]["name"] == "get_price"

    def test_on_llm_error_clears_pending_state(self):
        """An LLM error between start and end should pop the pending
        entry so the handler's internal dict doesn't grow unbounded.
        No LlmCall row should be written on error."""
        calls = []
        handler = CaptureCallbackHandler(run_id=42, ticker="NVDA", save_call=calls.append)
        from uuid import uuid4
        rid = uuid4()
        handler.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[HumanMessage(content="hello")]],
            run_id=rid,
        )
        # The pending entry exists after the start callback.
        assert rid in handler._pending
        handler.on_llm_error(RuntimeError("rate limit"), run_id=rid)
        # Pending state was cleared; no call was persisted.
        assert rid not in handler._pending
        assert calls == []

    def test_on_llm_error_is_safe_for_unknown_run_id(self):
        """Errors for a run_id we never saw must be a no-op, not a crash."""
        from uuid import uuid4
        handler = CaptureCallbackHandler(run_id=42, ticker="NVDA", save_call=lambda _: None)
        # Should not raise.
        handler.on_llm_error(RuntimeError("orphan error"), run_id=uuid4())
