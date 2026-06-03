"""Unit tests for the claude-code provider adapter.

Mocks ``claude_agent_sdk.query`` so the suite runs in CI without
touching the subscription or the local ``claude`` CLI. Phase-2b tests
exercise the LangChain-tool -> SDK-MCP bridge using lightweight tool
stubs — the real SDK MCP plumbing runs in-process so no Claude calls
are made even when ``_build_mcp_server`` fires for real.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

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


def _fake_tool(
    name: str,
    *,
    description: str = "test tool",
    side_effect: Optional[Callable[[dict], Any]] = None,
    tool_call_schema: Optional[type] = None,
    args_schema: Optional[type] = None,
) -> Any:
    """Minimal LangChain-style tool stub: name, description, schemas, ainvoke."""

    class _Tool:
        pass

    t = _Tool()
    t.name = name
    t.description = description
    t.tool_call_schema = tool_call_schema
    t.args_schema = args_schema

    async def _ainvoke(args: dict):
        if side_effect is None:
            return f"default-result-for-{name}"
        return side_effect(args)

    t.ainvoke = _ainvoke
    return t


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
    """``with_structured_output`` still raises so ``bind_structured`` keeps
    falling back to free-text for the manager/trader/portfolio agents."""

    def test_with_structured_output_raises(self):
        llm = mod.ClaudeCodeChatModel()
        with pytest.raises(NotImplementedError, match="structured_output"):
            llm.with_structured_output(dict)


@pytest.mark.unit
class TestBindTools:
    """Phase-2b ``bind_tools`` returns a new instance carrying the tools.
    Original instance must stay untouched (LangChain pipelines build
    multiple bound variants from the same base model)."""

    def test_bind_tools_returns_new_instance(self):
        base = mod.ClaudeCodeChatModel(model="claude-sonnet-4-6")
        bound = base.bind_tools([_fake_tool("echo")])
        assert isinstance(bound, mod.ClaudeCodeChatModel)
        assert bound is not base
        assert base.bound_tools is None
        assert bound.bound_tools and bound.bound_tools[0].name == "echo"
        assert bound.model == "claude-sonnet-4-6"

    def test_bind_tools_empty_list_clears_binding(self):
        base = mod.ClaudeCodeChatModel()
        assert base.bind_tools([]).bound_tools is None

    def test_bind_tools_none_clears_binding(self):
        base = mod.ClaudeCodeChatModel()
        assert base.bind_tools(None).bound_tools is None

    def test_bind_tools_supports_multiple_tools(self):
        base = mod.ClaudeCodeChatModel()
        bound = base.bind_tools([_fake_tool("a"), _fake_tool("b")])
        names = [t.name for t in bound.bound_tools]
        assert names == ["a", "b"]


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


# ---------------------------------------------------------------------------
# Phase-2b: MCP bridge
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMcpBridgeOptions:
    """Verify ``_aquery`` wires MCP server + bypassPermissions only when
    tools are bound, and keeps host isolation intact in both modes."""

    def test_bound_tools_inject_mcp_server_and_bypass_perms(self, monkeypatch):
        captured: dict[str, Any] = {}

        async def fake_query(prompt, options):
            captured["options"] = options
            yield _assistant("ok")
            yield _result()

        _patch_query(monkeypatch, fake_query)
        llm = mod.ClaudeCodeChatModel().bind_tools([_fake_tool("calc")])
        asyncio.run(llm._aquery(None, "ask"))

        opts = captured["options"]
        assert "tradingagents" in opts.mcp_servers
        assert opts.permission_mode == "bypassPermissions"
        # Host isolation must remain in place when tools are bound.
        assert opts.tools == []
        assert opts.skills == []
        assert opts.setting_sources == []
        assert opts.strict_mcp_config is True

    def test_unbound_skips_mcp_server_and_permission_mode(self, monkeypatch):
        captured: dict[str, Any] = {}

        async def fake_query(prompt, options):
            captured["options"] = options
            yield _assistant("ok")
            yield _result()

        _patch_query(monkeypatch, fake_query)
        llm = mod.ClaudeCodeChatModel()
        asyncio.run(llm._aquery(None, "ask"))

        opts = captured["options"]
        # Default dict is fine — must not contain our namespace.
        assert "tradingagents" not in (opts.mcp_servers or {})
        # No permission mode override when nothing is bound.
        assert opts.permission_mode is None
        # Silence-during-tools directive only fires when tools are bound.
        assert "Tool-use output rules" not in opts.system_prompt

    def test_silence_directive_appended_when_bound(self, monkeypatch):
        captured: dict[str, Any] = {}

        async def fake_query(prompt, options):
            captured["options"] = options
            yield _assistant("ok")
            yield _result()

        _patch_query(monkeypatch, fake_query)
        llm = mod.ClaudeCodeChatModel().bind_tools([_fake_tool("t")])
        asyncio.run(llm._aquery("Be an analyst.", "q"))

        prompt = captured["options"].system_prompt
        # Caller's prompt preserved verbatim at the head.
        assert prompt.startswith("Be an analyst.")
        # Directive appended below — any of the load-bearing phrases works.
        assert "Tool-use output rules" in prompt
        assert "do not narrate" in prompt


@pytest.mark.unit
class TestWrapLangchainTool:
    """Handler envelope, error containment, and result stringification."""

    def test_string_result_wrapped_as_text_content(self):
        tool = _fake_tool("echo", side_effect=lambda args: f"got {args['x']}")
        wrapped = mod.ClaudeCodeChatModel._wrap_langchain_tool(tool)
        assert wrapped.name == "echo"
        result = asyncio.run(wrapped.handler({"x": 42}))
        assert result == {"content": [{"type": "text", "text": "got 42"}]}
        assert "is_error" not in result

    def test_non_string_result_is_stringified(self):
        tool = _fake_tool("dict_tool", side_effect=lambda args: {"key": "val"})
        wrapped = mod.ClaudeCodeChatModel._wrap_langchain_tool(tool)
        result = asyncio.run(wrapped.handler({}))
        body = result["content"][0]["text"]
        assert "'key'" in body and "'val'" in body

    def test_tool_exception_yields_is_error(self):
        def boom(_args):
            raise ValueError("boom")

        tool = _fake_tool("fail", side_effect=boom)
        wrapped = mod.ClaudeCodeChatModel._wrap_langchain_tool(tool)
        result = asyncio.run(wrapped.handler({}))
        assert result["is_error"] is True
        assert "fail failed" in result["content"][0]["text"]
        assert "ValueError: boom" in result["content"][0]["text"]

    def test_handler_invokes_tool_with_provided_args(self):
        seen: dict[str, Any] = {}

        def remember(args):
            seen.update(args)
            return "ok"

        tool = _fake_tool("spy", side_effect=remember)
        wrapped = mod.ClaudeCodeChatModel._wrap_langchain_tool(tool)
        asyncio.run(wrapped.handler({"a": 1, "b": "two"}))
        assert seen == {"a": 1, "b": "two"}


@pytest.mark.unit
class TestExtractInputSchema:
    """Schema source precedence: tool_call_schema > args_schema > fallback."""

    class _Schema1(BaseModel):
        x: int

    class _Schema2(BaseModel):
        y: str

    def test_prefers_tool_call_schema(self):
        tool = _fake_tool("t", tool_call_schema=self._Schema1, args_schema=self._Schema2)
        schema = mod.ClaudeCodeChatModel._extract_input_schema(tool)
        assert schema["type"] == "object"
        assert "x" in schema["properties"]
        assert "y" not in schema["properties"]

    def test_falls_back_to_args_schema(self):
        tool = _fake_tool("t", tool_call_schema=None, args_schema=self._Schema2)
        schema = mod.ClaudeCodeChatModel._extract_input_schema(tool)
        assert "y" in schema["properties"]

    def test_empty_object_when_no_schema(self):
        tool = _fake_tool("t")
        assert mod.ClaudeCodeChatModel._extract_input_schema(tool) == {
            "type": "object", "properties": {}
        }


@pytest.mark.unit
class TestBuildMcpServer:
    """``create_sdk_mcp_server`` is in-process so this exercises the real
    SDK side without touching Claude."""

    def test_returns_non_none_config(self):
        server = mod.ClaudeCodeChatModel._build_mcp_server(
            [_fake_tool("a"), _fake_tool("b")]
        )
        assert server is not None

    def test_empty_tool_list_still_constructs(self):
        # Edge case — bind_tools clears bound_tools when called with [],
        # so this shouldn't fire in practice, but the helper should not
        # crash if called directly.
        server = mod.ClaudeCodeChatModel._build_mcp_server([])
        assert server is not None


# ---------------------------------------------------------------------------
# Error-only partial text: detect + retry once
# ---------------------------------------------------------------------------


def _scripted_query(*attempts):
    """fake_query that returns a different message script on each successive
    invocation. Lets us simulate "first attempt errors, second succeeds"
    flows without mocking the SDK's internals."""
    state = {"i": 0}

    async def fake(prompt, options):
        i = state["i"]
        state["i"] += 1
        for m in attempts[i]:
            yield m

    fake.state = state  # exposed for assertions on call count
    return fake


@pytest.mark.unit
class TestLooksLikeErrorText:
    """Pure heuristic — covers every branch of the detector."""

    def test_empty_text_is_not_error(self):
        assert mod.ClaudeCodeChatModel._looks_like_error_text("", None) is False

    def test_short_text_with_api_error_prefix_is_error(self):
        assert mod.ClaudeCodeChatModel._looks_like_error_text(
            "API Error: The socket connection was closed unexpectedly.", None
        ) is True

    def test_short_text_with_lowercase_api_error_is_error(self):
        assert mod.ClaudeCodeChatModel._looks_like_error_text(
            "API error: rate limited", None
        ) is True

    def test_short_text_with_leading_whitespace_handled(self):
        assert mod.ClaudeCodeChatModel._looks_like_error_text(
            "\n   API Error: x", None
        ) is True

    def test_short_text_without_known_prefix_is_not_error(self):
        # Short *legit* responses must pass through (e.g. "42" from the
        # calculator smoke must not be misclassified).
        assert mod.ClaudeCodeChatModel._looks_like_error_text("42", None) is False
        assert mod.ClaudeCodeChatModel._looks_like_error_text(
            "Buy.", None
        ) is False

    def test_long_text_with_error_prefix_is_not_error(self):
        # A 500-char reply starting with "Error:" is almost certainly the
        # model legitimately discussing an error in its output, not a
        # CLI failure notice. Sanity threshold prevents over-retry.
        text = "Error: " + ("x" * 500)
        assert mod.ClaudeCodeChatModel._looks_like_error_text(text, None) is False

    def test_rate_limit_429_suppresses_retry(self):
        class FakeResult:
            api_error_status = 429

        # Even if the text looks like a soft failure, 429 means quota —
        # immediate retry is wasted.
        assert mod.ClaudeCodeChatModel._looks_like_error_text(
            "API Error: rate limited", FakeResult()
        ) is False

    def test_non_429_api_error_status_still_retries(self):
        class FakeResult:
            api_error_status = 500

        assert mod.ClaudeCodeChatModel._looks_like_error_text(
            "API Error: server error", FakeResult()
        ) is True


@pytest.mark.unit
class TestRetryFlow:
    """End-to-end retry behaviour through ``_aquery``."""

    def test_error_only_text_triggers_retry_then_succeeds(
        self, monkeypatch, caplog
    ):
        fake = _scripted_query(
            # Attempt 1: SDK delivers a 70-char "API Error..." TextBlock.
            [
                _assistant("API Error: The socket connection was closed unexpectedly."),
                _result(),
            ],
            # Attempt 2: model writes the real report.
            [_assistant("The real analyst report goes here."), _result()],
        )
        _patch_query(monkeypatch, fake)

        llm = mod.ClaudeCodeChatModel()
        with caplog.at_level(logging.WARNING, logger=ADAPTER_LOGGER):
            text = asyncio.run(llm._aquery(None, "ask"))

        assert text == "The real analyst report goes here."
        assert fake.state["i"] == 2  # two query() invocations
        msgs = [r.getMessage() for r in caplog.records]
        assert any("retrying once" in m for m in msgs)

    def test_double_failure_raises_runtime_error(self, monkeypatch):
        fake = _scripted_query(
            [_assistant("API Error: socket closed"), _result()],
            [_assistant("API Error: socket closed again"), _result()],
        )
        _patch_query(monkeypatch, fake)

        llm = mod.ClaudeCodeChatModel()
        with pytest.raises(RuntimeError, match="error-only text on both attempts"):
            asyncio.run(llm._aquery(None, "ask"))
        assert fake.state["i"] == 2

    def test_429_skips_retry(self, monkeypatch):
        # Rate limit on attempt 1 — must NOT spend a second attempt; the
        # short error text is returned to the caller so the surrounding
        # ``invoke_structured_or_freetext`` can decide what to do with it.
        fake = _scripted_query(
            [
                _assistant("API Error: rate limited"),
                _result(is_error=True, api_error_status=429),
            ],
        )
        _patch_query(monkeypatch, fake)

        llm = mod.ClaudeCodeChatModel()
        text = asyncio.run(llm._aquery(None, "ask"))
        assert text == "API Error: rate limited"
        assert fake.state["i"] == 1  # no retry consumed

    def test_clean_first_attempt_does_not_retry(self, monkeypatch):
        fake = _scripted_query(
            [_assistant("A normal, well-formed reply."), _result()],
        )
        _patch_query(monkeypatch, fake)

        llm = mod.ClaudeCodeChatModel()
        text = asyncio.run(llm._aquery(None, "ask"))
        assert text == "A normal, well-formed reply."
        assert fake.state["i"] == 1
