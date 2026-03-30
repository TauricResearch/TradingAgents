import os
import unittest
from unittest.mock import patch

from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.openai_client import OpenAIClient
from tradingagents.llm_clients.validators import validate_model


class LLMProviderSupportTests(unittest.TestCase):
    def test_factory_supports_deepseek_and_kimi(self):
        deepseek_client = create_llm_client("deepseek", "deepseek-chat")
        kimi_client = create_llm_client("kimi", "kimi-latest")

        self.assertIsInstance(deepseek_client, OpenAIClient)
        self.assertIsInstance(kimi_client, OpenAIClient)

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_deepseek_uses_expected_base_url_and_key(self, mock_chat_openai):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "deepseek-test-key"}, clear=False):
            client = OpenAIClient("deepseek-chat", provider="deepseek")
            client.get_llm()

        kwargs = mock_chat_openai.call_args.kwargs
        self.assertEqual(kwargs["base_url"], "https://api.deepseek.com/v1")
        self.assertEqual(kwargs["api_key"], "deepseek-test-key")
        self.assertEqual(kwargs["model"], "deepseek-chat")

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_kimi_prefers_kimi_api_key(self, mock_chat_openai):
        with patch.dict(
            os.environ,
            {
                "KIMI_API_KEY": "kimi-test-key",
                "MOONSHOT_API_KEY": "moonshot-test-key",
            },
            clear=False,
        ):
            client = OpenAIClient("kimi-latest", provider="kimi")
            client.get_llm()

        kwargs = mock_chat_openai.call_args.kwargs
        self.assertEqual(kwargs["base_url"], "https://api.moonshot.cn/v1")
        self.assertEqual(kwargs["api_key"], "kimi-test-key")
        self.assertEqual(kwargs["model"], "kimi-latest")

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_kimi_falls_back_to_moonshot_key(self, mock_chat_openai):
        with patch.dict(
            os.environ,
            {"KIMI_API_KEY": "", "MOONSHOT_API_KEY": "moonshot-test-key"},
            clear=False,
        ):
            client = OpenAIClient("kimi-thinking-preview", provider="kimi")
            client.get_llm()

        kwargs = mock_chat_openai.call_args.kwargs
        self.assertEqual(kwargs["base_url"], "https://api.moonshot.cn/v1")
        self.assertEqual(kwargs["api_key"], "moonshot-test-key")
        self.assertEqual(kwargs["model"], "kimi-thinking-preview")

    def test_validator_allows_fast_moving_compatibility_providers(self):
        self.assertTrue(validate_model("deepseek", "any-model-name"))
        self.assertTrue(validate_model("kimi", "any-model-name"))


if __name__ == "__main__":
    unittest.main()
