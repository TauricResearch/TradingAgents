import unittest
from unittest.mock import Mock
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
    def test_deprecated_preview_model_uses_stable_fallback(self, mock_chat):
        client = GoogleClient("gemini-3.1-flash-lite-preview", api_key="test-key")

        with self.assertWarns(UserWarning):
            client.get_llm()

        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs.get("model"), "gemini-2.5-flash-lite")

    @patch("tradingagents.llm_clients.google_client.time.sleep")
    @patch("tradingagents.llm_clients.google_client.ChatGoogleGenerativeAI.invoke")
    def test_429_waits_60_seconds_and_retries_once(self, mock_parent_invoke, mock_sleep):
        mock_parent_invoke.side_effect = [
            Exception("429 rate limit exceeded"),
            Mock(content="ok"),
        ]

        client = GoogleClient("gemini-2.5-flash", api_key="test-key")
        llm = client.get_llm()

        with self.assertWarns(RuntimeWarning):
            response = llm.invoke("hello")

        self.assertEqual(response.content, "ok")
        mock_sleep.assert_called_once_with(60)
        self.assertEqual(mock_parent_invoke.call_count, 2)

    @patch("tradingagents.llm_clients.google_client.time.sleep")
    @patch("tradingagents.llm_clients.google_client.ChatGoogleGenerativeAI.invoke")
    def test_non_429_error_does_not_sleep_or_retry(self, mock_parent_invoke, mock_sleep):
        mock_parent_invoke.side_effect = Exception("500 internal server error")

        client = GoogleClient("gemini-2.5-flash", api_key="test-key")
        llm = client.get_llm()

        with self.assertRaises(Exception):
            llm.invoke("hello")

        mock_sleep.assert_not_called()
        self.assertEqual(mock_parent_invoke.call_count, 1)


if __name__ == "__main__":
    unittest.main()
