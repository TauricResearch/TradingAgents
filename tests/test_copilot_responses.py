"""Regression tests for GPT-6 via GitHub Copilot's Responses API."""

import os
import unittest
from unittest.mock import patch

from tradingagents.llm_clients.openai_client import OpenAIClient


class CopilotResponsesTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-token"})
    def test_copilot_host_uses_responses_api_and_required_headers(self):
        llm = OpenAIClient(
            "gpt-6-luna",
            base_url="https://api.githubcopilot.com",
            provider="openai",
        ).get_llm()

        self.assertTrue(llm.use_responses_api)
        self.assertEqual(llm.default_headers["Copilot-Integration-Id"], "vscode-chat")
        self.assertEqual(llm.default_headers["Openai-Intent"], "conversation-edits")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-token"})
    def test_other_custom_openai_compatible_host_keeps_chat_completions(self):
        llm = OpenAIClient(
            "gpt-6-luna",
            base_url="https://gateway.example.test/v1",
            provider="openai",
        ).get_llm()

        self.assertFalse(llm.use_responses_api)
        self.assertFalse(llm.default_headers)


if __name__ == "__main__":
    unittest.main()
