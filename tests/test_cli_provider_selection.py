import unittest
from unittest.mock import patch

from cli.utils import select_llm_provider


class CliProviderSelectionTests(unittest.TestCase):
    @patch("cli.utils.questionary.select")
    def test_select_llm_provider_returns_internal_provider_key(self, mock_select):
        mock_select.return_value.ask.return_value = (
            "ollama",
            "http://localhost:4000/v1",
            "Ollama / llama.cpp",
        )

        provider, url = select_llm_provider()

        self.assertEqual(provider, "ollama")
        self.assertEqual(url, "http://localhost:4000/v1")


if __name__ == "__main__":
    unittest.main()
