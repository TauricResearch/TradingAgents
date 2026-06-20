import os
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

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


# =========================================================================
# Tests merged from test_final_push.py and test_llm_and_minor.py
# =========================================================================


class GoogleClientEdgeTests(unittest.TestCase):
    """Lines 17, 33, 50-58."""

    def test_normalized_chat_google_invoke(self):
        from tradingagents.llm_clients.google_client import NormalizedChatGoogleGenerativeAI

        client = NormalizedChatGoogleGenerativeAI(model="gemini-3-pro", google_api_key="test")
        raw_response = MagicMock()
        raw_response.content = "normalized"
        with patch.object(NormalizedChatGoogleGenerativeAI, "invoke", wraps=client.invoke), \
             patch("langchain_google_genai.ChatGoogleGenerativeAI.invoke", return_value=raw_response), \
             patch("tradingagents.llm_clients.google_client.normalize_content",
                   return_value=raw_response) as mock_norm:
            result = client.invoke("hello")
        self.assertEqual(result.content, "normalized")

    def test_get_llm_with_base_url(self):
        from tradingagents.llm_clients.google_client import GoogleClient
        import tradingagents.llm_clients.google_client as mod

        captured = {}
        with patch.object(mod, "NormalizedChatGoogleGenerativeAI", lambda **kwargs: captured.__setitem__("kwargs", kwargs)):
            client = GoogleClient(model="gemini-3-pro", base_url="https://custom.google.com", google_api_key="test")
            client.get_llm()
        self.assertEqual(captured["kwargs"]["base_url"], "https://custom.google.com")

    def test_get_llm_without_base_url(self):
        from tradingagents.llm_clients.google_client import GoogleClient
        import tradingagents.llm_clients.google_client as mod

        captured = {}
        with patch.object(mod, "NormalizedChatGoogleGenerativeAI", lambda **kwargs: captured.__setitem__("kwargs", kwargs)):
            client = GoogleClient(model="gemini-3-pro", google_api_key="test")
            client.get_llm()
        self.assertNotIn("base_url", captured["kwargs"])

    def test_thinking_level_gemini_3_pro_minimal_to_low(self):
        from tradingagents.llm_clients.google_client import GoogleClient
        import tradingagents.llm_clients.google_client as mod

        captured = {}
        with patch.object(mod, "NormalizedChatGoogleGenerativeAI", lambda **kwargs: captured.__setitem__("kwargs", kwargs)):
            client = GoogleClient(model="gemini-3-pro", thinking_level="minimal", google_api_key="test")
            client.get_llm()
        self.assertEqual(captured["kwargs"]["thinking_level"], "low")

    def test_thinking_level_gemini_3_flash_preserves_minimal(self):
        from tradingagents.llm_clients.google_client import GoogleClient
        import tradingagents.llm_clients.google_client as mod

        captured = {}
        with patch.object(mod, "NormalizedChatGoogleGenerativeAI", lambda **kwargs: captured.__setitem__("kwargs", kwargs)):
            client = GoogleClient(model="gemini-3-flash", thinking_level="minimal", google_api_key="test")
            client.get_llm()
        self.assertEqual(captured["kwargs"]["thinking_level"], "minimal")

    def test_thinking_level_gemini_25_high_sets_budget(self):
        from tradingagents.llm_clients.google_client import GoogleClient
        import tradingagents.llm_clients.google_client as mod

        captured = {}
        with patch.object(mod, "NormalizedChatGoogleGenerativeAI", lambda **kwargs: captured.__setitem__("kwargs", kwargs)):
            client = GoogleClient(model="gemini-2.5-pro", thinking_level="high", google_api_key="test")
            client.get_llm()
        self.assertEqual(captured["kwargs"]["thinking_budget"], -1)

    def test_thinking_level_gemini_25_low_sets_budget(self):
        from tradingagents.llm_clients.google_client import GoogleClient
        import tradingagents.llm_clients.google_client as mod

        captured = {}
        with patch.object(mod, "NormalizedChatGoogleGenerativeAI", lambda **kwargs: captured.__setitem__("kwargs", kwargs)):
            client = GoogleClient(model="gemini-2.5-flash", thinking_level="low", google_api_key="test")
            client.get_llm()
        self.assertEqual(captured["kwargs"]["thinking_budget"], 0)

    def test_get_llm_missing_model_raises(self):
        from tradingagents.llm_clients.google_client import GoogleClient
        client = GoogleClient("", google_api_key="test")
        with self.assertRaises(ValueError):
            client.get_llm()

    def test_google_api_key_resolution(self):
        from tradingagents.llm_clients.google_client import GoogleClient
        import tradingagents.llm_clients.google_client as mod

        captured = {}
        with patch.object(mod, "NormalizedChatGoogleGenerativeAI", lambda **kwargs: captured.__setitem__("kwargs", kwargs)):
            client = GoogleClient(model="gemini-3-pro", api_key="unified-key", google_api_key="specific-key")
            client.get_llm()
        self.assertEqual(captured["kwargs"]["google_api_key"], "unified-key")

    def test_google_api_key_fallback(self):
        from tradingagents.llm_clients.google_client import GoogleClient
        import tradingagents.llm_clients.google_client as mod

        captured = {}
        with patch.object(mod, "NormalizedChatGoogleGenerativeAI", lambda **kwargs: captured.__setitem__("kwargs", kwargs)):
            client = GoogleClient(model="gemini-3-pro", google_api_key="specific-key")
            client.get_llm()
        self.assertEqual(captured["kwargs"]["google_api_key"], "specific-key")


class TestGoogleClient(unittest.TestCase):

    def test_validate_model(self):
        """Line 62–64: validate_model delegates."""
        from tradingagents.llm_clients.google_client import GoogleClient

        with patch(
            "tradingagents.llm_clients.google_client.validate_model",
            return_value=True,
        ):
            client = GoogleClient("gemini-2.5-flash")
            self.assertTrue(client.validate_model())

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_thinking_level_gemini3_pro_minimal_to_low(self, mock_chat):
        """Lines 51–53: Gemini 3 Pro with 'minimal' is remapped to 'low'."""
        from tradingagents.llm_clients.google_client import GoogleClient

        client = GoogleClient(
            "gemini-3-pro", thinking_level="minimal", api_key="x"
        )
        client.get_llm()
        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs["thinking_level"], "low")

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_thinking_level_gemini3_flash_minimal_passes(self, mock_chat):
        """Line 55: Gemini 3 Flash accepts 'minimal'."""
        from tradingagents.llm_clients.google_client import GoogleClient

        client = GoogleClient(
            "gemini-3-flash", thinking_level="minimal", api_key="x"
        )
        client.get_llm()
        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs["thinking_level"], "minimal")

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_thinking_level_gemini3_pro_high_passes(self, mock_chat):
        """Line 55: Gemini 3 Pro with 'high' passes through."""
        from tradingagents.llm_clients.google_client import GoogleClient

        client = GoogleClient(
            "gemini-3-pro", thinking_level="high", api_key="x"
        )
        client.get_llm()
        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs["thinking_level"], "high")

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_thinking_level_gemini25_high_to_budget(self, mock_chat):
        """Line 58: Gemini 2.5 with 'high' maps to thinking_budget = -1."""
        from tradingagents.llm_clients.google_client import GoogleClient

        client = GoogleClient(
            "gemini-2.5-flash", thinking_level="high", api_key="x"
        )
        client.get_llm()
        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs["thinking_budget"], -1)

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_thinking_level_gemini25_low_to_budget_zero(self, mock_chat):
        """Line 58: Gemini 2.5 with 'low' maps to thinking_budget = 0."""
        from tradingagents.llm_clients.google_client import GoogleClient

        client = GoogleClient(
            "gemini-2.5-flash", thinking_level="low", api_key="x"
        )
        client.get_llm()
        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs["thinking_budget"], 0)

    @patch("tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_thinking_level_none_skips(self, mock_chat):
        """Line 49: no thinking_level means no key added."""
        from tradingagents.llm_clients.google_client import GoogleClient

        client = GoogleClient("gemini-2.5-flash", api_key="x")
        client.get_llm()
        call_kwargs = mock_chat.call_args[1]
        self.assertNotIn("thinking_level", call_kwargs)
        self.assertNotIn("thinking_budget", call_kwargs)


if __name__ == "__main__":
    unittest.main()
