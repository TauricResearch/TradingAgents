"""Tests verifying the github_copilot provider plumbing through the
OpenAI-compatible client route.

GitHub's OpenAI-compatible inference endpoint (``https://models.github.ai/
inference``) is reached via the existing ``OpenAIClient``: the factory
routes provider ``"github_copilot"`` into the OpenAI bucket, and the
client picks up the GITHUB_TOKEN env var plus the GitHub Models base URL.

Mirrors tests/test_google_api_key.py in spirit (small, focused, mocked).
"""

import unittest
from unittest.mock import patch

import pytest

from tradingagents.llm_clients.factory import create_llm_client


@pytest.mark.unit
class TestGitHubCopilotApiKeyHandling(unittest.TestCase):
    """Verify GITHUB_TOKEN auth flows correctly through OpenAIClient."""

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_github_token_env_picked_up(self, mock_chat):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "env-token-xyz"}, clear=False):
            client = create_llm_client("github_copilot", "openai/gpt-4o")
            client.get_llm()

        kwargs = mock_chat.call_args.kwargs
        self.assertEqual(kwargs.get("api_key"), "env-token-xyz")
        self.assertEqual(kwargs.get("base_url"), "https://models.github.ai/inference")

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_explicit_api_key_overrides_env(self, mock_chat):
        # User-supplied api_key flows through the OpenAIClient passthrough
        # set; the env-based fallback is only used when no api_key is given.
        with patch.dict("os.environ", {"GITHUB_TOKEN": "env-token"}, clear=False):
            client = create_llm_client(
                "github_copilot",
                "openai/gpt-4o",
                api_key="explicit-token",
            )
            client.get_llm()

        kwargs = mock_chat.call_args.kwargs
        self.assertEqual(kwargs.get("api_key"), "explicit-token")

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_explicit_base_url_overrides_default(self, mock_chat):
        # An explicit base_url (e.g. corporate proxy) wins over the default.
        client = create_llm_client(
            "github_copilot",
            "openai/gpt-4o",
            base_url="https://proxy.example/v1",
        )
        client.get_llm()

        kwargs = mock_chat.call_args.kwargs
        self.assertEqual(kwargs.get("base_url"), "https://proxy.example/v1")


if __name__ == "__main__":
    unittest.main()
