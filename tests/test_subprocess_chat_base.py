"""Unit tests for the SubprocessChatModel base class.

Uses a fake subclass + a mocked subprocess.run so the tests don't depend on
any real CLI being installed. Validates the contract every concrete provider
(claude_code, gemini_cli, ...) inherits.
"""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tradingagents.llm_clients.subprocess_chat_base import SubprocessChatModel


class _FakeProc:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class _FakeChat(SubprocessChatModel):
    """Minimal concrete subclass that returns canned responses."""

    canned_text: str = ""
    canned_structured: Optional[Any] = None

    @property
    def _llm_type(self) -> str:
        return "fake_cli"

    def _binary_name(self) -> str:
        return "fake-cli"

    def _binary_env_var(self) -> str:
        return "FAKE_CLI_BIN"

    def _build_command(
        self,
        binary: str,
        system_prompt: str,
        json_schema: Optional[Dict[str, Any]],
    ) -> List[str]:
        return [binary, "-p", "--system-prompt", system_prompt]

    def _parse_response(
        self,
        stdout: str,
        json_schema: Optional[Dict[str, Any]],
    ) -> Tuple[str, Optional[Any]]:
        return self.canned_text, self.canned_structured


@pytest.mark.unit
class TestSubprocessChatModelMessageRendering(unittest.TestCase):
    def test_system_messages_concatenate_into_system_prompt(self):
        chat = _FakeChat(model="x")
        sys, user = chat._render_messages(
            [
                SystemMessage(content="Be concise."),
                SystemMessage(content="Use plain English."),
                HumanMessage(content="Hello."),
            ]
        )
        self.assertIn("Be concise.", sys)
        self.assertIn("Use plain English.", sys)
        self.assertIn("### user\nHello.", user)

    def test_assistant_tool_calls_serialized_back_into_history(self):
        chat = _FakeChat(model="x")
        ai = AIMessage(
            content="",
            tool_calls=[{"name": "get_stock_data", "args": {"sym": "AAPL"}, "id": "x"}],
        )
        sys, user = chat._render_messages(
            [HumanMessage(content="fetch"), ai, ToolMessage(content="data!", tool_call_id="x", name="get_stock_data")]
        )
        # Round-trip: the assistant block contains the JSON envelope
        self.assertIn('"tool_calls"', user)
        self.assertIn("get_stock_data", user)
        # ToolMessage gets a tool[name] block
        self.assertIn("### tool[get_stock_data]", user)

    def test_bound_tools_inject_protocol_into_system_prompt(self):
        @tool
        def echo(text: str) -> str:
            """Echo a string back."""
            return text

        chat = _FakeChat(model="x").bind_tools([echo])
        sys, _ = chat._render_messages([HumanMessage(content="hi")])
        self.assertIn("TOOL PROTOCOL", sys)
        self.assertIn("echo", sys)


@pytest.mark.unit
class TestSubprocessChatModelToolEnvelope(unittest.TestCase):
    def test_pure_json_envelope(self):
        env = SubprocessChatModel._extract_tool_envelope('{"tool_calls": [{"name": "f", "args": {"a": 1}}]}')
        self.assertIsNotNone(env)
        self.assertEqual(env["tool_calls"][0]["name"], "f")

    def test_envelope_wrapped_in_prose(self):
        text = (
            "Sure, let me fetch that for you.\n"
            '{"tool_calls": [{"name": "fetch", "args": {"id": 42}}]}\n'
            "Hope this helps!"
        )
        env = SubprocessChatModel._extract_tool_envelope(text)
        self.assertIsNotNone(env)
        self.assertEqual(env["tool_calls"][0]["args"]["id"], 42)

    def test_no_envelope_returns_none(self):
        self.assertIsNone(SubprocessChatModel._extract_tool_envelope("Just regular prose."))

    def test_parse_tool_calls_assigns_ids(self):
        calls = SubprocessChatModel._parse_tool_calls({"tool_calls": [{"name": "f", "args": {"a": 1}}]})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["name"], "f")
        self.assertTrue(calls[0]["id"].startswith("call_"))
        self.assertEqual(calls[0]["type"], "tool_call")


@pytest.mark.unit
class TestSubprocessChatModelGenerate(unittest.TestCase):
    @patch(
        "tradingagents.llm_clients.subprocess_chat_base.shutil.which",
        return_value="/usr/local/bin/fake-cli",
    )
    @patch("tradingagents.llm_clients.subprocess_chat_base.subprocess.run")
    def test_generate_returns_text_when_no_tool_envelope(self, mock_run, _which):
        mock_run.return_value = _FakeProc(stdout='{"ignored": true}')
        chat = _FakeChat(model="x", canned_text="Hello world")
        result = chat.invoke([HumanMessage(content="hi")])
        self.assertIsInstance(result, AIMessage)
        self.assertEqual(result.content, "Hello world")
        self.assertFalse(result.tool_calls)

    @patch(
        "tradingagents.llm_clients.subprocess_chat_base.shutil.which",
        return_value="/usr/local/bin/fake-cli",
    )
    @patch("tradingagents.llm_clients.subprocess_chat_base.subprocess.run")
    def test_generate_extracts_tool_calls_when_bound(self, mock_run, _which):
        mock_run.return_value = _FakeProc(stdout='{"ignored": true}')

        @tool
        def fetch(sym: str) -> str:
            """Fetch by symbol."""
            return ""

        chat = _FakeChat(
            model="x",
            canned_text='{"tool_calls": [{"name": "fetch", "args": {"sym": "AAPL"}}]}',
        ).bind_tools([fetch])
        result = chat.invoke([HumanMessage(content="get AAPL")])
        self.assertEqual(result.content, "")
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0]["name"], "fetch")
        self.assertEqual(result.tool_calls[0]["args"]["sym"], "AAPL")

    @patch(
        "tradingagents.llm_clients.subprocess_chat_base.shutil.which",
        return_value="/usr/local/bin/fake-cli",
    )
    @patch("tradingagents.llm_clients.subprocess_chat_base.subprocess.run")
    def test_generate_prefers_structured_output_over_text(self, mock_run, _which):
        mock_run.return_value = _FakeProc(stdout="{}")

        class Out(BaseModel):
            verdict: str = Field(...)
            score: int = Field(...)

        chat = _FakeChat(
            model="x",
            canned_text="ignored prose",
            canned_structured={"verdict": "buy", "score": 9},
        )
        result = chat.with_structured_output(Out).invoke([HumanMessage(content="?")])
        self.assertIsInstance(result, Out)
        self.assertEqual(result.verdict, "buy")
        self.assertEqual(result.score, 9)

    @patch(
        "tradingagents.llm_clients.subprocess_chat_base.shutil.which",
        return_value="/usr/local/bin/fake-cli",
    )
    @patch("tradingagents.llm_clients.subprocess_chat_base.subprocess.run")
    def test_subprocess_failure_raises_with_stderr(self, mock_run, _which):
        mock_run.return_value = _FakeProc(returncode=1, stderr="boom: not authenticated")
        chat = _FakeChat(model="x")
        with self.assertRaises(RuntimeError) as ctx:
            chat.invoke([HumanMessage(content="hi")])
        self.assertIn("not authenticated", str(ctx.exception))


@pytest.mark.unit
class TestSubprocessChatModelBinaryResolution(unittest.TestCase):
    @patch(
        "tradingagents.llm_clients.subprocess_chat_base.shutil.which",
        return_value=None,
    )
    def test_missing_binary_raises_clear_error(self, _which):
        chat = _FakeChat(model="x")
        with self.assertRaises(RuntimeError) as ctx:
            chat._resolve_binary()
        self.assertIn("fake-cli", str(ctx.exception))
        self.assertIn("FAKE_CLI_BIN", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
