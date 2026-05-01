import os
import unittest
from unittest.mock import patch

import pytest

from tradingagents.llm_clients.google_client import GoogleClient


@pytest.mark.unit
class TestGoogleApiKeyStandardization(unittest.TestCase):
    """Verify GoogleClient accepts unified api_key parameter."""

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_api_key_handling(self, mock_chat):
        test_cases = [
            ("unified api_key is mapped", {"api_key": "test-key-123"}, "test-key-123"),
            ("legacy google_api_key still works", {"google_api_key": "legacy-key-456"}, "legacy-key-456"),
            ("unified api_key takes precedence", {"api_key": "unified", "google_api_key": "legacy"}, "unified"),
        ]

        for msg, kwargs, expected_key in test_cases:
            with self.subTest(msg=msg):
                mock_chat.reset_mock()
                client = GoogleClient("gemini-2.5-flash", **kwargs)
                client.get_llm()
                call_kwargs = mock_chat.call_args[1]
                self.assertEqual(call_kwargs.get("google_api_key"), expected_key)

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_google_api_key_falls_back_to_environment(self, mock_chat):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "env-google-key"}, clear=True):
            client = GoogleClient("gemini-2.5-flash")
            client.get_llm()

        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs.get("google_api_key"), "env-google-key")

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_gemini_api_key_is_supported_as_environment_fallback(self, mock_chat):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-gemini-key"}, clear=True):
            client = GoogleClient("gemini-2.5-flash")
            client.get_llm()

        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs.get("google_api_key"), "env-gemini-key")


if __name__ == "__main__":
    unittest.main()
