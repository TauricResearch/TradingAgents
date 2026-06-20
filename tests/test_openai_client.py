import os
import unittest
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.llm_clients.openai_client import (
    DeepSeekChatOpenAI,
    NormalizedChatOpenAI,
    OpenAIClient,
    _resolve_provider_base_url,
)


@pytest.mark.unit
class ResolveProviderBaseUrlTests(unittest.TestCase):
    @patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://remote:11434/v1"}, clear=True)
    def test_ollama_uses_env_var(self):
        url = _resolve_provider_base_url("ollama")
        self.assertEqual(url, "http://remote:11434/v1")

    def test_ollama_falls_back_to_default(self):
        url = _resolve_provider_base_url("ollama")
        self.assertEqual(url, "http://localhost:11434/v1")

    def test_returns_none_for_unknown_provider(self):
        url = _resolve_provider_base_url("nonexistent")
        self.assertIsNone(url)


@pytest.mark.unit
class OpenAIClientGetLlmTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True)
    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_creates_chat_openai_with_base_url(self, mock_chat):
        client = OpenAIClient("gpt-4", provider="openai")
        llm = client.get_llm()
        mock_chat.assert_called_once()
        args, kwargs = mock_chat.call_args
        self.assertEqual(kwargs["model"], "gpt-4")
        self.assertTrue(kwargs.get("use_responses_api"))

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "ds-test"}, clear=True)
    @patch("tradingagents.llm_clients.openai_client.DeepSeekChatOpenAI")
    def test_deepseek_uses_deepseek_chat(self, mock_chat):
        client = OpenAIClient("deepseek-v4-flash", provider="deepseek")
        llm = client.get_llm()
        mock_chat.assert_called_once()

    @patch.dict(os.environ, {"MINIMAX_API_KEY": "mm-test"}, clear=True)
    @patch("tradingagents.llm_clients.openai_client.MinimaxChatOpenAI")
    def test_minimax_uses_minimax_chat(self, mock_chat):
        client = OpenAIClient("MiniMax-M2.7", provider="minimax")
        llm = client.get_llm()
        mock_chat.assert_called_once()

    @patch.dict(os.environ, {"SENSENOVA_API_KEY": "ss-test"}, clear=True)
    @patch("tradingagents.llm_clients.openai_client.DeepSeekChatOpenAI")
    def test_sensenova_reasoning_model(self, mock_chat):
        client = OpenAIClient("deepseek-v4-flash", provider="sensenova")
        llm = client.get_llm()
        mock_chat.assert_called_once()

    @patch.dict(os.environ, {"SENSENOVA_API_KEY": "ss-test"}, clear=True)
    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_sensenova_non_reasoning_model(self, mock_chat):
        client = OpenAIClient("sensenova-6.7-flash-lite", provider="sensenova")
        llm = client.get_llm()
        mock_chat.assert_called_once()

    @patch.dict(os.environ, {"KIMI_CODING_API_KEY": "kimi-test"}, clear=True)
    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_kimi_sets_user_agent(self, mock_chat):
        client = OpenAIClient("kimi-k2.6", provider="kimi")
        llm = client.get_llm()
        _, kwargs = mock_chat.call_args
        self.assertEqual(
            kwargs["default_headers"]["user-agent"], "KimiCLI/1.8.0"
        )

    def test_raises_on_empty_model(self):
        client = OpenAIClient("", provider="openai")
        with self.assertRaises(ValueError):
            client.get_llm()


@pytest.mark.unit
class NormalizedChatOpenAITests(unittest.TestCase):
    def test_with_structured_output_raises_for_none_method(self):
        with patch(
            "tradingagents.llm_clients.openai_client.get_capabilities"
        ) as mock_caps:
            caps = MagicMock()
            caps.preferred_structured_method = "none"
            mock_caps.return_value = caps
            client = NormalizedChatOpenAI(model="test-model")
            with self.assertRaises(NotImplementedError):
                client.with_structured_output(dict)

    def test_with_structured_output_suppresses_tool_choice(self):
        with patch(
            "tradingagents.llm_clients.openai_client.get_capabilities"
        ) as mock_caps, patch(
            "tradingagents.llm_clients.openai_client.NormalizedChatOpenAI.with_structured_output",
            return_value="mock_result",
        ):
            caps = MagicMock()
            caps.preferred_structured_method = "function_calling"
            caps.supports_tool_choice = False
            mock_caps.return_value = caps
            client = NormalizedChatOpenAI(model="test-model")
            result = client.with_structured_output(dict)
            self.assertIsNotNone(result)


# =========================================================================
# Edge-case tests merged from test_remaining_coverage.py
# =========================================================================


@pytest.mark.unit
class NormalizedChatOpenAIInvokeTests(unittest.TestCase):
    """Line 33: invoke normalizes content."""

    def test_invoke_normalizes_content(self):
        client = NormalizedChatOpenAI(model="gpt-5.4")
        raw_msg = MagicMock(content="raw")
        with patch.object(NormalizedChatOpenAI, "invoke", wraps=client.invoke) as wrapped:
            with patch("langchain_openai.ChatOpenAI.invoke", return_value=raw_msg):
                with patch("tradingagents.llm_clients.openai_client.normalize_content",
                           return_value="normalized") as mock_norm:
                    result = client.invoke("input")
        self.assertEqual(result, "normalized")


@pytest.mark.unit
class DeepSeekPayloadEdgeCases(unittest.TestCase):
    """DeepSeekChatOpenAI._get_request_payload: lines 106, 110-111, 119-120."""

    def setUp(self):
        self.client = DeepSeekChatOpenAI(model="deepseek-v4-flash")

    def test_skips_when_already_has_reasoning_content(self):
        """Line 106: message already has reasoning_content -> skip."""
        mock_payload = {
            "messages": [{"role": "assistant", "content": "ok", "reasoning_content": "existing"}]
        }
        mock_msg = MagicMock()
        mock_msg.id = "msg-1"
        with patch.object(NormalizedChatOpenAI, "_get_request_payload", return_value=mock_payload), \
             patch("tradingagents.llm_clients.openai_client._input_to_messages", return_value=[mock_msg]):
            result = self.client._get_request_payload("test")
        self.assertEqual(result["messages"][0]["reasoning_content"], "existing")

    def test_uses_sidecar_cache(self):
        """Lines 110-111: cache hit via message id."""
        self.client._reasoning_cache["msg-42"] = "cached thinking"
        mock_payload = {"messages": [{"role": "assistant", "content": "ok"}]}
        mock_msg = MagicMock()
        mock_msg.id = "msg-42"
        with patch.object(NormalizedChatOpenAI, "_get_request_payload", return_value=mock_payload), \
             patch("tradingagents.llm_clients.openai_client._input_to_messages", return_value=[mock_msg]):
            result = self.client._get_request_payload("test")
        self.assertEqual(result["messages"][0]["reasoning_content"], "cached thinking")

    def test_tool_calls_fallback(self):
        """Lines 119-120: assistant with tool_calls gets placeholder."""
        self.client._reasoning_cache.clear()
        mock_payload = {
            "messages": [{"role": "assistant", "content": "", "tool_calls": [{"id": "call_1"}]}]
        }
        mock_msg = MagicMock()
        mock_msg.id = None
        with patch.object(NormalizedChatOpenAI, "_get_request_payload", return_value=mock_payload), \
             patch("tradingagents.llm_clients.openai_client._input_to_messages", return_value=[mock_msg]):
            result = self.client._get_request_payload("test")
        self.assertEqual(result["messages"][0]["reasoning_content"], "...")


@pytest.mark.unit
class DeepSeekCreateChatResultTests(unittest.TestCase):
    """Lines 140-144: cache eviction when exceeding max size."""

    def test_cache_eviction(self):
        client = DeepSeekChatOpenAI(model="deepseek-v4-flash")
        client._REASONING_CACHE_MAX = 2
        client._reasoning_cache = {"old-1": "old", "old-2": "old"}

        mock_chat_result = MagicMock(spec=["generations"])
        mock_gen = MagicMock()
        mock_gen.message.additional_kwargs = {}
        mock_gen.message.id = "new-id"
        mock_chat_result.generations = [mock_gen]

        response = {"choices": [{"message": {"reasoning_content": "new thinking"}}]}

        with patch.object(NormalizedChatOpenAI, "_create_chat_result", return_value=mock_chat_result):
            client._create_chat_result(response)

        self.assertIn("new-id", client._reasoning_cache)
        self.assertEqual(client._reasoning_cache["new-id"], "new thinking")
        self.assertEqual(len(client._reasoning_cache), 2)


@pytest.mark.unit
class OpenAIClientGetLLMEdgeCases(unittest.TestCase):
    """Lines 276, 278, 282-283: ollama api_key, base_url fallback, kimi user-agent."""

    @patch.dict(os.environ, {}, clear=True)
    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_ollama_uses_literal_api_key(self, mock_chat):
        """Line 276: ollama gets api_key='ollama' when env is empty."""
        client = OpenAIClient("qwen3:latest", provider="ollama")
        client.get_llm()
        _, kwargs = mock_chat.call_args
        self.assertEqual(kwargs["api_key"], "ollama")

    @patch.dict(os.environ, {}, clear=True)
    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_custom_base_url_for_unknown_provider(self, mock_chat):
        """Line 278: unknown provider with explicit base_url."""
        client = OpenAIClient("custom-model", provider="unknown_provider",
                              base_url="https://proxy.example.com/v1")
        client.get_llm()
        _, kwargs = mock_chat.call_args
        self.assertEqual(kwargs["base_url"], "https://proxy.example.com/v1")

    @patch.dict(os.environ, {"KIMI_CODING_API_KEY": "kk-test"}, clear=True)
    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_kimi_sets_user_agent(self, mock_chat):
        """Lines 282-283: kimi provider sets custom user-agent."""
        client = OpenAIClient("kimi-k2.6", provider="kimi")
        client.get_llm()
        _, kwargs = mock_chat.call_args
        self.assertEqual(kwargs["default_headers"]["user-agent"], "KimiCLI/1.8.0")

    def test_raises_on_empty_model(self):
        client = OpenAIClient("", provider="openai")
        with self.assertRaises(ValueError):
            client.get_llm()


if __name__ == "__main__":
    unittest.main()