import unittest
from unittest.mock import patch


class TestGoogleApiKeyStandardization(unittest.TestCase):
    """Verify GoogleClient accepts unified api_key parameter."""

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_api_key_mapped_to_google_api_key(self, mock_chat):
        from tradingagents.llm_clients.google_client import GoogleClient

        client = GoogleClient("gemini-2.5-flash", api_key="test-key-123")
        client.get_llm()
        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs["google_api_key"], "test-key-123")

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_legacy_google_api_key_still_works(self, mock_chat):
        from tradingagents.llm_clients.google_client import GoogleClient

        client = GoogleClient("gemini-2.5-flash", google_api_key="legacy-key-456")
        client.get_llm()
        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs["google_api_key"], "legacy-key-456")

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_api_key_takes_precedence_over_google_api_key(self, mock_chat):
        from tradingagents.llm_clients.google_client import GoogleClient

        client = GoogleClient(
            "gemini-2.5-flash", api_key="unified", google_api_key="legacy"
        )
        client.get_llm()
        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs["google_api_key"], "unified")


if __name__ == "__main__":
    unittest.main()
