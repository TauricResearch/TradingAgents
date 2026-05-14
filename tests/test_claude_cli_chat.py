"""Unit tests for the Claude CLI Chat model wrapper.

Tests cover:
- Message formatting (system, human, assistant, multi-turn, multi-part content)
- JSON response parsing
- Stop sequence handling
- Subprocess invocation (mocked)
- Error handling (timeout, exit codes, empty output, auth errors)
- Retry logic with exponential backoff
- bind_tools no-op behavior
- with_structured_output rejection
- Factory integration
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from tradingagents.llm_clients.claude_cli_chat import (
    ClaudeCLIChat,
    _apply_stop_sequences,
    _extract_text,
    _find_claude_binary,
    _format_messages,
    _parse_json_response,
)


# ── Binary discovery ─────────────────────────────────────────────────────


class TestFindClaudeBinary:
    @patch("tradingagents.llm_clients.claude_cli_chat.shutil.which", return_value=None)
    def test_raises_when_not_on_path(self, _):
        with pytest.raises(FileNotFoundError, match="not found on PATH"):
            _find_claude_binary()

    @patch("tradingagents.llm_clients.claude_cli_chat.shutil.which", return_value="/usr/bin/claude")
    def test_returns_path_when_found(self, _):
        assert _find_claude_binary() == "/usr/bin/claude"


# ── Message formatting ────────────────────────────────────────────────────


class TestFormatMessages:
    def test_system_and_human(self):
        msgs = [SystemMessage(content="You are helpful"), HumanMessage(content="Hi")]
        system, user = _format_messages(msgs)
        assert system == "You are helpful"
        assert "[Human]" in user
        assert "Hi" in user

    def test_multi_turn(self):
        msgs = [
            SystemMessage(content="System"),
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),
            HumanMessage(content="Q2"),
        ]
        system, user = _format_messages(msgs)
        assert system == "System"
        assert "[Human]\nQ1" in user
        assert "[Assistant]\nA1" in user
        assert "[Human]\nQ2" in user

    def test_no_system_message(self):
        msgs = [HumanMessage(content="Hello")]
        system, user = _format_messages(msgs)
        assert system == ""
        assert "Hello" in user

    def test_multiple_system_messages(self):
        msgs = [SystemMessage(content="Part 1"), SystemMessage(content="Part 2")]
        system, user = _format_messages(msgs)
        assert "Part 1" in system
        assert "Part 2" in system

    def test_empty_messages(self):
        system, user = _format_messages([])
        assert system == ""
        assert user == ""


class TestExtractText:
    def test_string_content(self):
        assert _extract_text("hello") == "hello"

    def test_list_content(self):
        content = [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "world"},
        ]
        assert _extract_text(content) == "hello\nworld"

    def test_list_with_non_text_blocks(self):
        content = [
            {"type": "reasoning", "text": "thinking..."},
            {"type": "text", "text": "answer"},
        ]
        result = _extract_text(content)
        assert "answer" in result

    def test_non_string_non_list(self):
        assert _extract_text(42) == "42"


# ── JSON response parsing ────────────────────────────────────────────────


class TestParseJsonResponse:
    def test_success_response(self):
        raw = json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Hello world",
        })
        assert _parse_json_response(raw) == "Hello world"

    def test_error_response(self):
        raw = json.dumps({
            "type": "result",
            "is_error": True,
            "result": "Rate limited",
        })
        with pytest.raises(RuntimeError, match="Rate limited"):
            _parse_json_response(raw)

    def test_invalid_json_raises(self):
        with pytest.raises(RuntimeError, match="invalid JSON"):
            _parse_json_response("not json at all")

    def test_missing_result_field(self):
        raw = json.dumps({"type": "something_else"})
        result = _parse_json_response(raw)
        assert isinstance(result, str)

    def test_null_result(self):
        raw = json.dumps({"type": "result", "result": None})
        # None result → unexpected shape fallback
        result = _parse_json_response(raw)
        assert isinstance(result, str)


# ── Stop sequences ───────────────────────────────────────────────────────


class TestStopSequences:
    def test_no_stop(self):
        assert _apply_stop_sequences("hello world", None) == "hello world"

    def test_empty_stop_list(self):
        assert _apply_stop_sequences("hello world", []) == "hello world"

    def test_single_stop(self):
        assert _apply_stop_sequences("hello STOP world", ["STOP"]) == "hello "

    def test_multiple_stops_earliest_wins(self):
        text = "aaa BBB ccc DDD eee"
        assert _apply_stop_sequences(text, ["DDD", "BBB"]) == "aaa "

    def test_stop_not_found(self):
        assert _apply_stop_sequences("hello world", ["MISSING"]) == "hello world"


# ── ClaudeCLIChat properties ─────────────────────────────────────────────


class TestClaudeCLIChatProperties:
    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    def test_llm_type(self, _):
        llm = ClaudeCLIChat()
        assert llm._llm_type == "claude_cli"

    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    def test_supports_tool_calls_false(self, _):
        llm = ClaudeCLIChat()
        assert llm.supports_tool_calls is False

    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    def test_bind_tools_returns_self(self, _):
        llm = ClaudeCLIChat()
        bound = llm.bind_tools([MagicMock(name="tool1")])
        assert bound is llm

    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    def test_with_structured_output_raises(self, _):
        llm = ClaudeCLIChat()
        with pytest.raises(NotImplementedError, match="structured output"):
            llm.with_structured_output({"type": "object"})

    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    def test_identifying_params(self, _):
        llm = ClaudeCLIChat(model_name="test-model", timeout=60)
        params = llm._identifying_params
        assert params["model_name"] == "test-model"
        assert params["timeout"] == 60


# ── Subprocess invocation (mocked) ───────────────────────────────────────


class TestGenerate:
    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    @patch("tradingagents.llm_clients.claude_cli_chat.subprocess.run")
    def test_successful_generation(self, mock_run, _):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "Test response",
            }).encode(),
            stderr=b"",
        )

        llm = ClaudeCLIChat()
        result = llm._generate([HumanMessage(content="Hello")])

        assert len(result.generations) == 1
        assert result.generations[0].message.content == "Test response"

    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    @patch("tradingagents.llm_clients.claude_cli_chat.subprocess.run")
    def test_stop_sequences_applied(self, mock_run, _):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "type": "result",
                "is_error": False,
                "result": "Part 1 STOP Part 2",
            }).encode(),
            stderr=b"",
        )

        llm = ClaudeCLIChat()
        result = llm._generate(
            [HumanMessage(content="Hello")],
            stop=["STOP"],
        )
        assert result.generations[0].message.content == "Part 1 "

    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    @patch("tradingagents.llm_clients.claude_cli_chat.subprocess.run")
    @patch("tradingagents.llm_clients.claude_cli_chat.time.sleep")
    def test_timeout_retries(self, mock_sleep, mock_run, _):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=300)

        llm = ClaudeCLIChat(max_retries=2)
        with pytest.raises(TimeoutError):
            llm._generate([HumanMessage(content="Hello")])

        assert mock_run.call_count == 2

    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    @patch("tradingagents.llm_clients.claude_cli_chat.subprocess.run")
    def test_auth_error_no_retry(self, mock_run, _):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=b"",
            stderr=b"401 authentication error",
        )

        llm = ClaudeCLIChat(max_retries=3)
        with pytest.raises(RuntimeError, match="authentication"):
            llm._generate([HumanMessage(content="Hello")])

        # Auth errors should NOT retry
        assert mock_run.call_count == 1

    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    @patch("tradingagents.llm_clients.claude_cli_chat.subprocess.run")
    @patch("tradingagents.llm_clients.claude_cli_chat.time.sleep")
    def test_rate_limit_retries(self, mock_sleep, mock_run, _):
        # First call rate limited, second succeeds
        mock_run.side_effect = [
            MagicMock(
                returncode=1,
                stdout=b"",
                stderr=b"rate limit exceeded",
            ),
            MagicMock(
                returncode=0,
                stdout=json.dumps({
                    "type": "result",
                    "is_error": False,
                    "result": "Success after retry",
                }).encode(),
                stderr=b"",
            ),
        ]

        llm = ClaudeCLIChat(max_retries=3)
        result = llm._generate([HumanMessage(content="Hello")])

        assert result.generations[0].message.content == "Success after retry"
        assert mock_run.call_count == 2

    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    @patch("tradingagents.llm_clients.claude_cli_chat.subprocess.run")
    def test_env_minimal(self, mock_run, _):
        """Verify subprocess receives minimal environment (WR-01 fix)."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "type": "result",
                "is_error": False,
                "result": "ok",
            }).encode(),
            stderr=b"",
        )

        llm = ClaudeCLIChat()
        llm._generate([HumanMessage(content="Hello")])

        call_kwargs = mock_run.call_args
        env = call_kwargs.kwargs.get("env") or call_kwargs[1].get("env")
        assert env is not None, "subprocess should receive explicit env"
        assert "OPENAI_API_KEY" not in env, "API keys should not leak to subprocess"


# ── Factory integration ──────────────────────────────────────────────────


class TestFactoryIntegration:
    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    def test_create_via_factory(self, _):
        from tradingagents.llm_clients.factory import create_llm_client
        client = create_llm_client("claude_cli", "default")
        llm = client.get_llm()
        assert type(llm).__name__ == "ClaudeCLIChat"
        assert llm.supports_tool_calls is False

    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    def test_create_with_model(self, _):
        from tradingagents.llm_clients.factory import create_llm_client
        client = create_llm_client("claude_cli", "claude-opus-4-6")
        llm = client.get_llm()
        assert llm.model_name == "claude-opus-4-6"

    @patch("tradingagents.llm_clients.claude_cli_chat._find_claude_binary", return_value="/usr/bin/claude")
    def test_create_with_timeout(self, _):
        from tradingagents.llm_clients.factory import create_llm_client
        client = create_llm_client("claude_cli", "default", timeout=60)
        llm = client.get_llm()
        assert llm.timeout == 60
