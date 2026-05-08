import unittest
import os
from unittest.mock import patch

import pytest

from cli.utils import select_llm_provider


class _PromptResult:
    def __init__(self, value):
        self.value = value

    def ask(self):
        return self.value


@pytest.mark.unit
class CliProviderSelectionTests(unittest.TestCase):
    @patch("cli.utils.questionary.text")
    @patch("cli.utils.questionary.confirm")
    @patch("cli.utils.questionary.select")
    def test_openai_keeps_default_backend_url_when_no_override(
        self,
        mock_select,
        mock_confirm,
        mock_text,
    ):
        mock_select.return_value = _PromptResult(("openai", "https://api.openai.com/v1"))
        mock_confirm.return_value = _PromptResult(False)

        provider, backend_url = select_llm_provider()

        self.assertEqual(provider, "openai")
        self.assertEqual(backend_url, "https://api.openai.com/v1")
        mock_text.assert_not_called()

    @patch("cli.utils.questionary.text")
    @patch("cli.utils.questionary.confirm")
    @patch("cli.utils.questionary.select")
    def test_openai_allows_custom_backend_url_override(
        self,
        mock_select,
        mock_confirm,
        mock_text,
    ):
        mock_select.return_value = _PromptResult(("openai", "https://api.openai.com/v1"))
        mock_confirm.return_value = _PromptResult(True)
        mock_text.return_value = _PromptResult("https://example-proxy.test/v1")

        provider, backend_url = select_llm_provider()

        self.assertEqual(provider, "openai")
        self.assertEqual(backend_url, "https://example-proxy.test/v1")

    @patch.dict(os.environ, {"OPENAI_BASE_URL": "https://env-proxy.example/v1"}, clear=False)
    @patch("cli.utils.questionary.text")
    @patch("cli.utils.questionary.confirm")
    @patch("cli.utils.questionary.select")
    def test_openai_uses_environment_backend_url_by_default(
        self,
        mock_select,
        mock_confirm,
        mock_text,
    ):
        mock_select.return_value = _PromptResult(("openai", "https://api.openai.com/v1"))
        mock_confirm.return_value = _PromptResult(False)

        provider, backend_url = select_llm_provider()

        self.assertEqual(provider, "openai")
        self.assertEqual(backend_url, "https://env-proxy.example/v1")
        mock_text.assert_not_called()

    @patch("cli.utils.console.print")
    @patch("cli.utils.questionary.text")
    @patch("cli.utils.questionary.confirm")
    @patch("cli.utils.questionary.select")
    def test_openai_exits_when_custom_backend_url_prompt_is_cancelled(
        self,
        mock_select,
        mock_confirm,
        mock_text,
        mock_print,
    ):
        mock_select.return_value = _PromptResult(("openai", "https://api.openai.com/v1"))
        mock_confirm.return_value = _PromptResult(True)
        mock_text.return_value = _PromptResult(None)

        with self.assertRaises(SystemExit):
            select_llm_provider()

        mock_print.assert_called_with("\n[red]No base URL provided. Exiting...[/red]")


if __name__ == "__main__":
    unittest.main()
