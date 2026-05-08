import os
import unittest
from unittest.mock import patch

import pytest

from tradingagents.llm_clients.openai_client import OpenAIClient


@pytest.mark.unit
class DefaultConfigEnvironmentTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_BASE_URL": "https://env-proxy.example/v1"}, clear=False)
    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_openai_base_url_env_populates_openai_client_default(
        self,
        mock_chat,
    ):
        client = OpenAIClient("gpt-5.4")
        client.get_llm()

        self.assertEqual(
            mock_chat.call_args.kwargs["base_url"],
            "https://env-proxy.example/v1",
        )


if __name__ == "__main__":
    unittest.main()
