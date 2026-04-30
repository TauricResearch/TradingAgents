"""Regression tests for the Anthropic-thinking + structured-output fix.

When Claude is served through GitHub Copilot (a ``ChatOpenAI``-shaped
client pointed at ``api.githubcopilot.com``), the model id encodes the
extended-thinking effort level via a suffix:
``claude-opus-4.7-xhigh``. Any structured-output call against that model
fails with::

    400 - Thinking may not be enabled when tool_choice forces tool use.

``bind_structured`` is supposed to detect this combination and build a
*non-thinking twin* (same model id with the suffix stripped) that can
accept the forced ``tool_choice`` LangChain emits for structured output.
The original thinking-enabled LLM stays in use everywhere else.

These tests stub the LLM so they don't hit the network — what we care
about is that the routing logic picks the right twin and falls back to
the original LLM when no remediation is possible.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from tradingagents.agents.utils import structured as struct_mod


class _DummyPlan(BaseModel):
    decision: str


# ---------------------------------------------------------------------------
# _strip_thinking_suffix
# ---------------------------------------------------------------------------


class TestStripThinkingSuffix:
    def test_strips_xhigh(self):
        assert struct_mod._strip_thinking_suffix("claude-opus-4.7-xhigh") == "claude-opus-4.7"

    def test_strips_high(self):
        assert struct_mod._strip_thinking_suffix("claude-opus-4.7-high") == "claude-opus-4.7"

    def test_strips_medium(self):
        assert struct_mod._strip_thinking_suffix("claude-sonnet-4.5-medium") == "claude-sonnet-4.5"

    def test_strips_low(self):
        assert struct_mod._strip_thinking_suffix("claude-haiku-4.5-low") == "claude-haiku-4.5"

    def test_strips_minimal(self):
        assert struct_mod._strip_thinking_suffix("claude-opus-4.7-minimal") == "claude-opus-4.7"

    def test_passthrough_when_no_suffix(self):
        # Plain Claude model ids (no thinking) should be returned unchanged.
        assert struct_mod._strip_thinking_suffix("claude-opus-4.7") == "claude-opus-4.7"

    def test_passthrough_for_non_string_input(self):
        # Defensive: don't blow up on None or non-string LLM model fields.
        assert struct_mod._strip_thinking_suffix(None) is None

    def test_does_not_strip_unrelated_dashes(self):
        # ``-4.7`` is a version segment, not an effort suffix — must stay.
        assert struct_mod._strip_thinking_suffix("claude-opus-4.7") == "claude-opus-4.7"


# ---------------------------------------------------------------------------
# _build_structured_twin
# ---------------------------------------------------------------------------


def _make_fake_chat_openai(model_name: str):
    """Build an LLM-shaped object that supports ``model_copy`` like a real
    pydantic ChatOpenAI instance, without actually constructing one (which
    would require a real API key)."""
    fake = MagicMock()
    fake.model_name = model_name
    # Simulate pydantic's model_copy: returns a *new* MagicMock with the
    # updated field. We track the swap so we can assert on it.
    def _model_copy(update=None):
        twin = MagicMock()
        twin.model_name = (update or {}).get("model_name", model_name)
        twin.with_structured_output = MagicMock(return_value="STRUCTURED_TWIN_OUTPUT")
        return twin
    fake.model_copy = _model_copy
    fake.with_structured_output = MagicMock(return_value="STRUCTURED_ORIGINAL_OUTPUT")
    return fake


def _make_fake_chat_anthropic(model: str):
    """Same pattern but using ``model`` (matches ChatAnthropic's field name)."""
    fake = MagicMock(spec=["model", "model_copy", "with_structured_output"])
    fake.model = model
    def _model_copy(update=None):
        twin = MagicMock(spec=["model", "with_structured_output"])
        twin.model = (update or {}).get("model", model)
        twin.with_structured_output = MagicMock(return_value="STRUCTURED_TWIN_OUTPUT")
        return twin
    fake.model_copy = _model_copy
    fake.with_structured_output = MagicMock(return_value="STRUCTURED_ORIGINAL_OUTPUT")
    return fake


class TestBuildStructuredTwin:
    def test_claude_with_thinking_suffix_returns_stripped_twin(self):
        llm = _make_fake_chat_openai("claude-opus-4.7-xhigh")
        twin = struct_mod._build_structured_twin(llm)
        # The twin must be a different object with the suffix stripped.
        assert twin is not llm
        assert getattr(twin, "model_name", None) == "claude-opus-4.7"

    def test_claude_without_thinking_suffix_returns_original(self):
        llm = _make_fake_chat_openai("claude-opus-4.7")
        twin = struct_mod._build_structured_twin(llm)
        assert twin is llm  # no remediation needed

    def test_non_claude_model_returns_original(self):
        # GPT-5 with reasoning effort doesn't have the same restriction.
        llm = _make_fake_chat_openai("gpt-5.5")
        twin = struct_mod._build_structured_twin(llm)
        assert twin is llm

    def test_chat_anthropic_with_suffix_returns_stripped_twin(self):
        # Direct Anthropic provider also encodes effort in newer langchain
        # versions — make sure we handle that too.
        llm = _make_fake_chat_anthropic("claude-opus-4.7-xhigh")
        twin = struct_mod._build_structured_twin(llm)
        assert twin is not llm
        assert getattr(twin, "model", None) == "claude-opus-4.7"

    def test_failure_to_clone_falls_back_to_original_llm(self):
        # If model_copy itself blows up, we must not propagate — log and
        # return the original so the call site degrades to free-text
        # rather than crashing.
        llm = _make_fake_chat_openai("claude-opus-4.7-xhigh")
        llm.model_copy = MagicMock(side_effect=RuntimeError("clone failed"))
        twin = struct_mod._build_structured_twin(llm)
        assert twin is llm

    def test_llm_with_no_model_attribute_returns_original(self):
        llm = MagicMock(spec=["with_structured_output"])  # no model/model_name
        # Strip out auto-attributes from MagicMock so getattr returns None.
        twin = struct_mod._build_structured_twin(llm)
        assert twin is llm


# ---------------------------------------------------------------------------
# bind_structured integration
# ---------------------------------------------------------------------------


class TestBindStructuredAnthropicTwin:
    def test_thinking_enabled_claude_binds_structured_via_twin(self):
        """The bug-fix path: claude-opus-4.7-xhigh must produce a structured
        binding sourced from the *twin* (claude-opus-4.7), not the original."""
        llm = _make_fake_chat_openai("claude-opus-4.7-xhigh")
        bound = struct_mod.bind_structured(llm, _DummyPlan, "Research Manager")
        # Twin's with_structured_output sentinel — must be the value used.
        assert bound == "STRUCTURED_TWIN_OUTPUT"
        # Original LLM's with_structured_output must NOT have been called.
        assert llm.with_structured_output.call_count == 0

    def test_non_thinking_claude_uses_original_llm(self):
        llm = _make_fake_chat_openai("claude-opus-4.7")
        bound = struct_mod.bind_structured(llm, _DummyPlan, "Research Manager")
        assert bound == "STRUCTURED_ORIGINAL_OUTPUT"
        assert llm.with_structured_output.call_count == 1

    def test_gpt5_uses_original_llm(self):
        llm = _make_fake_chat_openai("gpt-5.5")
        bound = struct_mod.bind_structured(llm, _DummyPlan, "Research Manager")
        assert bound == "STRUCTURED_ORIGINAL_OUTPUT"
        assert llm.with_structured_output.call_count == 1

    def test_unsupported_provider_returns_none(self):
        # Some older Ollama models don't support structured output at all
        # — the helper must return None so the agent uses free text.
        llm = MagicMock()
        llm.model_name = "llama-3.2"
        llm.with_structured_output = MagicMock(side_effect=NotImplementedError)
        bound = struct_mod.bind_structured(llm, _DummyPlan, "Trader")
        assert bound is None
