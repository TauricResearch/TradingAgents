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
        assert events[0]["data"]["text_preview"] is None


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
