"""Unit tests for the claude-code provider adapter (phase-1 scope).

Mocks ``claude_agent_sdk.query`` so the suite runs in CI without
touching the subscription or the local ``claude`` CLI.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import claude_agent_sdk as sdk
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from tradingagents.llm_clients import claude_code_client as mod
from tradingagents.llm_clients.factory import create_llm_client


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

ADAPTER_LOGGER = "tradingagents.llm_clients.claude_code_client"


def _assistant(text: str) -> AssistantMessage:
    return AssistantMessage(content=[TextBlock(text=text)], model="claude-sonnet-4-6")


def _result(
    *,
    usage: dict | None = None,
    is_error: bool = False,
    subtype: str = "success",
    duration_ms: int = 1000,
    duration_api_ms: int = 800,
    num_turns: int = 1,
    api_error_status: int | None = None,
) -> ResultMessage:
    return ResultMessage(
        subtype=subtype,
        duration_ms=duration_ms,
        duration_api_ms=duration_api_ms,
        is_error=is_error,
        num_turns=num_turns,
        session_id="sess",
        usage=usage
        or {
            "input_tokens": 100,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 50,
        },
        api_error_status=api_error_status,
    )


def _patch_query(monkeypatch, fake) -> None:
    """Replace ``claude_agent_sdk.query`` for the duration of one test."""
    monkeypatch.setattr(sdk, "query", fake)


# ---------------------------------------------------------------------------
# _flatten_messages
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFlattenMessages:
    def test_human_only_becomes_body(self):
        system, body = mod._flatten_messages([HumanMessage(content="hello")])
        assert system is None
        assert body == "hello"

    def test_system_message_extracted(self):
        system, body = mod._flatten_messages(
            [SystemMessage(content="be terse"), HumanMessage(content="hi")]
        )
        assert system == "be terse"
        assert body == "hi"

    def test_prior_ai_turn_prepended_with_marker(self):
        system, body = mod._flatten_messages(
            [
                HumanMessage(content="q1"),
                AIMessage(content="a1"),
                HumanMessage(content="q2"),
            ]
        )
        assert system is None
        assert "[Previous assistant turn]\na1" in body
        assert "q1" in body and "q2" in body

    def test_multiple_system_messages_joined(self):
        system, _ = mod._flatten_messages(
            [
                SystemMessage(content="rule1"),
                SystemMessage(content="rule2"),
                HumanMessage(content="q"),
            ]
        )
        assert system == "rule1\n\nrule2"

    def test_empty_list_returns_empty_pair(self):
        system, body = mod._flatten_messages([])
        assert system is None
        assert body == ""


# ---------------------------------------------------------------------------
# factory + client wiring
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFactoryWiring:
    def test_factory_returns_claude_code_client(self):
        c = create_llm_client("claude-code", "claude-sonnet-4-6")
        assert isinstance(c, mod.ClaudeCodeClient)
        assert c.get_provider_name() == "claude-code"

    def test_validate_known_model(self):
        c = create_llm_client("claude-code", "claude-sonnet-4-6")
        assert c.validate_model() is True

    def test_validate_unknown_model(self):
        c = create_llm_client("claude-code", "claude-mystery-0-0")
        assert c.validate_model() is False

    def test_base_url_rejected(self):
        with pytest.raises(ValueError, match="no base_url"):
            create_llm_client(
                "claude-code", "claude-sonnet-4-6", base_url="https://x"
            )

    def test_get_llm_returns_chat_model(self):
        llm = create_llm_client("claude-code", "claude-sonnet-4-6").get_llm()
        assert isinstance(llm, mod.ClaudeCodeChatModel)
        assert llm._llm_type == "claude-code"
        assert llm.model == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# phase-1 contracts
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPhase1Contracts:
    """``bind_structured`` catches both NotImplementedError below; verify the
    adapter still refuses them so the fall-back path actually fires."""

    def test_bind_tools_raises(self):
        llm = mod.ClaudeCodeChatModel()
        with pytest.raises(NotImplementedError, match="bind_tools"):
            llm.bind_tools([])

    def test_with_structured_output_raises(self):
        llm = mod.ClaudeCodeChatModel()
        with pytest.raises(NotImplementedError, match="structured_output"):
            llm.with_structured_output(dict)


# ---------------------------------------------------------------------------
# _aquery with mocked SDK
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAquery:
    def test_collects_text_blocks(self, monkeypatch):
        async def fake_query(prompt, options):
            yield _assistant("hello ")
            yield _assistant("world")
            yield _result()

        _patch_query(monkeypatch, fake_query)
        llm = mod.ClaudeCodeChatModel(model="claude-sonnet-4-6")
        text = asyncio.run(llm._aquery(None, "ask"))
        assert text == "hello world"

    def test_passes_isolation_options(self, monkeypatch):
        captured: dict[str, Any] = {}

        async def fake_query(prompt, options):
            captured["prompt"] = prompt
            captured["options"] = options
            yield _assistant("ok")
            yield _result()

        _patch_query(monkeypatch, fake_query)
        llm = mod.ClaudeCodeChatModel(model="claude-sonnet-4-6")
        asyncio.run(llm._aquery("be terse", "question"))

        opts = captured["options"]
        # All four isolation knobs that prevent host Claude Code leak.
        assert opts.tools == []
        assert opts.skills == []
        assert opts.setting_sources == []
        assert opts.strict_mcp_config is True
        # Caller-provided system prompt wins.
        assert opts.system_prompt == "be terse"
        assert opts.model == "claude-sonnet-4-6"
        assert captured["prompt"] == "question"

    def test_default_system_prompt_when_caller_omits(self, monkeypatch):
        captured: dict[str, Any] = {}

        async def fake_query(prompt, options):
            captured["options"] = options
            yield _assistant("ok")
            yield _result()

        _patch_query(monkeypatch, fake_query)
        llm = mod.ClaudeCodeChatModel()
        asyncio.run(llm._aquery(None, "x"))
        # Must be a string (not None / not the Claude Code preset object),
        # so the CLI doesn't auto-load its default agent preamble.
        assert isinstance(captured["options"].system_prompt, str)
        assert captured["options"].system_prompt  # non-empty

    def test_partial_text_recovery_on_post_stream_error(
        self, monkeypatch, caplog
    ):
        async def fake_query(prompt, options):
            yield _assistant("partial answer")
            # Mirrors the documented 429/500/529 path where the CLI emits
            # is_error=True+subtype=success and exits non-zero.
            yield _result(is_error=True, api_error_status=429)
            raise RuntimeError(
                "Claude Code returned an error result: success"
            )

        _patch_query(monkeypatch, fake_query)
        llm = mod.ClaudeCodeChatModel()
        with caplog.at_level(logging.WARNING, logger=ADAPTER_LOGGER):
            text = asyncio.run(llm._aquery(None, "ask"))
        assert text == "partial answer"
        msgs = [r.getMessage() for r in caplog.records]
        assert any("finalization error suppressed" in m for m in msgs)
        assert any("api_error_status=429" in m for m in msgs)

    def test_empty_response_re_raises(self, monkeypatch):
        async def fake_query(prompt, options):
            if False:  # make this an async generator without yielding
                yield  # pragma: no cover
            raise RuntimeError("connection refused")

        _patch_query(monkeypatch, fake_query)
        llm = mod.ClaudeCodeChatModel()
        with pytest.raises(RuntimeError, match="connection refused"):
            asyncio.run(llm._aquery(None, "ask"))


# ---------------------------------------------------------------------------
# usage logging
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUsageLogging:
    def test_usage_line_emitted_on_success(self, monkeypatch, caplog):
        usage = {
            "input_tokens": 200,
            "output_tokens": 80,
            "cache_creation_input_tokens": 22000,
            "cache_read_input_tokens": 5000,
        }

        async def fake_query(prompt, options):
            yield _assistant("ok")
            yield _result(
                usage=usage, duration_ms=2500, duration_api_ms=2200, num_turns=1
            )

        _patch_query(monkeypatch, fake_query)
        llm = mod.ClaudeCodeChatModel(model="claude-sonnet-4-6")
        with caplog.at_level(logging.INFO, logger=ADAPTER_LOGGER):
            asyncio.run(llm._aquery(None, "ask"))

        usage_lines = [
            r.getMessage() for r in caplog.records if "claude-code usage" in r.getMessage()
        ]
        assert len(usage_lines) == 1
        line = usage_lines[0]
        assert "model=claude-sonnet-4-6" in line
        assert "input=200" in line
        assert "output=80" in line
        assert "cache_create=22000" in line
        assert "cache_read=5000" in line
        assert "duration=2.50s" in line

    def test_no_usage_log_when_result_message_absent(self, monkeypatch, caplog):
        async def fake_query(prompt, options):
            yield _assistant("ok")
            # Intentionally no ResultMessage.

        _patch_query(monkeypatch, fake_query)
        llm = mod.ClaudeCodeChatModel()
        with caplog.at_level(logging.INFO, logger=ADAPTER_LOGGER):
            asyncio.run(llm._aquery(None, "ask"))
        assert not [
            r for r in caplog.records if "claude-code usage" in r.getMessage()
        ]
