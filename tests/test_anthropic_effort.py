"""Tests for Anthropic effort-parameter gating (#831).

Haiku 4.5 (and current Haiku versions) reject the ``effort`` parameter
with a 400. Opus 4.5+ and Sonnet 4.5+ accept it. The gate uses a
forward-compat regex so future ``claude-{opus,sonnet}-X-Y`` releases
inherit support automatically.
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

from tradingagents.llm_clients import anthropic_client as mod


def _capture_kwargs(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        mod, "NormalizedChatAnthropic",
        lambda **kwargs: captured.setdefault("kwargs", kwargs),
    )
    return captured


@pytest.mark.unit
class TestEffortGate:
    @pytest.mark.parametrize(
        "model",
        ["claude-haiku-4-5", "claude-haiku-5-0", "claude-haiku-4-7-preview"],
    )
    def test_haiku_does_not_receive_effort(self, monkeypatch, model):
        captured = _capture_kwargs(monkeypatch)
        mod.AnthropicClient(model=model, effort="medium", api_key="x").get_llm()
        assert "effort" not in captured["kwargs"]

    @pytest.mark.parametrize(
        "model",
        [
            "claude-opus-4-5", "claude-opus-4-6", "claude-opus-4-7",
            "claude-sonnet-4-5", "claude-sonnet-4-6",
        ],
    )
    def test_current_opus_and_sonnet_receive_effort(self, monkeypatch, model):
        captured = _capture_kwargs(monkeypatch)
        mod.AnthropicClient(model=model, effort="high", api_key="x").get_llm()
        assert captured["kwargs"]["effort"] == "high"

    @pytest.mark.parametrize(
        "model",
        ["claude-opus-5-0", "claude-opus-4-8", "claude-sonnet-5-0"],
    )
    def test_future_opus_sonnet_inherit_effort_via_pattern(self, monkeypatch, model):
        """Forward-compat: new Opus/Sonnet versions don't need a code change."""
        captured = _capture_kwargs(monkeypatch)
        mod.AnthropicClient(model=model, effort="low", api_key="x").get_llm()
        assert captured["kwargs"]["effort"] == "low"

    def test_mythos_preview_receives_effort(self, monkeypatch):
        captured = _capture_kwargs(monkeypatch)
        mod.AnthropicClient(
            model="claude-mythos-preview", effort="medium", api_key="x"
        ).get_llm()
        assert captured["kwargs"]["effort"] == "medium"

    def test_unknown_anthropic_model_does_not_receive_effort(self, monkeypatch):
        """Default is conservative — unknown models don't get effort to avoid 400s."""
        captured = _capture_kwargs(monkeypatch)
        mod.AnthropicClient(
            model="claude-experimental-x", effort="medium", api_key="x"
        ).get_llm()
        assert "effort" not in captured["kwargs"]

    def test_other_kwargs_still_forwarded_when_effort_skipped(self, monkeypatch):
        """Skipping effort must not break other passthrough kwargs."""
        captured = _capture_kwargs(monkeypatch)
        mod.AnthropicClient(
            model="claude-haiku-4-5",
            effort="medium",
            api_key="placeholder",
            max_tokens=1024,
            timeout=30,
        ).get_llm()
        assert captured["kwargs"]["api_key"] == "placeholder"
        assert captured["kwargs"]["max_tokens"] == 1024
        assert captured["kwargs"]["timeout"] == 30
        assert "effort" not in captured["kwargs"]


# =========================================================================
# Tests merged from test_final_push.py and test_llm_and_minor.py
# =========================================================================


class AnthropicClientEdgeTests(unittest.TestCase):
    """Lines 44 (NormalizedChatAnthropic.invoke), 60 (base_url)."""

    def test_normalized_chat_anthropic_invoke(self):
        from tradingagents.llm_clients.anthropic_client import NormalizedChatAnthropic

        client = NormalizedChatAnthropic(model="claude-sonnet-4-5", api_key="test")
        raw_response = MagicMock()
        raw_response.content = "normalized result"
        with patch.object(NormalizedChatAnthropic, "invoke", wraps=client.invoke) as wrapped, \
             patch("langchain_anthropic.ChatAnthropic.invoke", return_value=raw_response), \
             patch("tradingagents.llm_clients.anthropic_client.normalize_content",
                   return_value=raw_response) as mock_norm:
            result = client.invoke("hello")
        self.assertEqual(result.content, "normalized result")

    def test_get_llm_with_base_url(self):
        from tradingagents.llm_clients.anthropic_client import AnthropicClient
        import tradingagents.llm_clients.anthropic_client as mod

        captured = {}
        with patch.object(mod, "NormalizedChatAnthropic", lambda **kwargs: captured.__setitem__("kwargs", kwargs)):
            client = AnthropicClient(model="claude-sonnet-4-5", base_url="https://custom.anthropic.com", api_key="test")
            client.get_llm()
        self.assertEqual(captured["kwargs"]["base_url"], "https://custom.anthropic.com")

    def test_get_llm_without_base_url(self):
        from tradingagents.llm_clients.anthropic_client import AnthropicClient
        import tradingagents.llm_clients.anthropic_client as mod

        captured = {}
        with patch.object(mod, "NormalizedChatAnthropic", lambda **kwargs: captured.__setitem__("kwargs", kwargs)):
            client = AnthropicClient(model="claude-sonnet-4-5", api_key="test")
            client.get_llm()
        self.assertNotIn("base_url", captured["kwargs"])

    def test_get_llm_missing_model_raises(self):
        from tradingagents.llm_clients.anthropic_client import AnthropicClient
        client = AnthropicClient("", api_key="test")
        with self.assertRaises(ValueError):
            client.get_llm()

    def test_get_llm_effort_skipped_for_haiku(self):
        from tradingagents.llm_clients.anthropic_client import AnthropicClient
        import tradingagents.llm_clients.anthropic_client as mod

        captured = {}
        with patch.object(mod, "NormalizedChatAnthropic", lambda **kwargs: captured.__setitem__("kwargs", kwargs)):
            client = AnthropicClient(model="claude-haiku-4-5", effort="high", api_key="test")
            client.get_llm()
        self.assertNotIn("effort", captured["kwargs"])


class TestAnthropicClient(unittest.TestCase):

    def test_validate_model(self):
        """Line 72–73: validate_model delegates."""
        from tradingagents.llm_clients.anthropic_client import AnthropicClient

        with patch(
            "tradingagents.llm_clients.anthropic_client.validate_model",
            return_value=True,
        ):
            client = AnthropicClient("claude-sonnet-4-5")
            self.assertTrue(client.validate_model())

    def test_get_llm_with_base_url(self):
        """Line 60: base_url passed through to NormalizedChatAnthropic."""
        from tradingagents.llm_clients.anthropic_client import AnthropicClient

        with patch(
            "tradingagents.llm_clients.anthropic_client.NormalizedChatAnthropic"
        ) as mock_cls:
            client = AnthropicClient(
                "claude-sonnet-4-5",
                base_url="https://custom.example.com",
                api_key="x",
            )
            client.get_llm()
        call_kwargs = mock_cls.call_args[1]
        self.assertIn("base_url", call_kwargs)
        self.assertEqual(call_kwargs["base_url"], "https://custom.example.com")

    def test_supports_effort_exact_match(self):
        """_supports_effort exact match."""
        from tradingagents.llm_clients.anthropic_client import _supports_effort

        self.assertTrue(_supports_effort("claude-mythos-preview"))

    def test_supports_effort_case_insensitive(self):
        """_supports_effort is case-insensitive."""
        from tradingagents.llm_clients.anthropic_client import _supports_effort

        self.assertTrue(_supports_effort("CLAUDE-OPUS-4-5"))
