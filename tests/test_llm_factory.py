import unittest
from unittest.mock import MagicMock, patch
from unittest.mock import patch as _patch

import pytest


@pytest.mark.unit
class OpenaiCompatibleListTests(unittest.TestCase):
    def test_includes_expected_providers(self):
        from tradingagents.llm_clients.factory import _OPENAI_COMPATIBLE

        self.assertIn("openai", _OPENAI_COMPATIBLE)
        self.assertIn("deepseek", _OPENAI_COMPATIBLE)

    def test_anthropic_not_in_openai_compatible(self):
        from tradingagents.llm_clients.factory import _OPENAI_COMPATIBLE

        self.assertNotIn("anthropic", _OPENAI_COMPATIBLE)

    def test_google_not_in_openai_compatible(self):
        from tradingagents.llm_clients.factory import _OPENAI_COMPATIBLE

        self.assertNotIn("google", _OPENAI_COMPATIBLE)

    def test_azure_not_in_openai_compatible(self):
        from tradingagents.llm_clients.factory import _OPENAI_COMPATIBLE

        self.assertNotIn("azure", _OPENAI_COMPATIBLE)


@pytest.mark.unit
class CreateLLMClientTests(unittest.TestCase):
    def test_unsupported_provider_raises(self):
        from tradingagents.llm_clients.factory import create_llm_client

        with self.assertRaises(ValueError):
            create_llm_client("nonexistent", "test")


@pytest.mark.unit
class CreateLLMClientIntegrationTests(unittest.TestCase):
    def test_openai_compatible_returns_base_llm_client(self):
        from tradingagents.llm_clients.base_client import BaseLLMClient
        from tradingagents.llm_clients.factory import create_llm_client

        for provider in ("openai", "deepseek", "qwen", "sensenova"):
            with self.subTest(provider=provider):
                client = create_llm_client(provider, "test-model")
                self.assertIsInstance(client, BaseLLMClient)

    def test_anthropic_returns_base_llm_client(self):
        from tradingagents.llm_clients.base_client import BaseLLMClient
        from tradingagents.llm_clients.factory import create_llm_client

        client = create_llm_client("anthropic", "claude-haiku-4-5")
        self.assertIsInstance(client, BaseLLMClient)

    def test_google_returns_base_llm_client(self):
        from tradingagents.llm_clients.base_client import BaseLLMClient
        from tradingagents.llm_clients.factory import create_llm_client

        client = create_llm_client("google", "gemini-2.5-flash")
        self.assertIsInstance(client, BaseLLMClient)

    def test_azure_returns_base_llm_client(self):
        from tradingagents.llm_clients.base_client import BaseLLMClient
        from tradingagents.llm_clients.factory import create_llm_client

        client = create_llm_client("azure", "gpt-4")
        self.assertIsInstance(client, BaseLLMClient)


if __name__ == "__main__":
    unittest.main()
