import warnings
import unittest
from unittest.mock import patch

from tradingagents.llm_clients.anthropic_client import AnthropicClient
from tradingagents.llm_clients.google_client import GoogleClient
from tradingagents.llm_clients.openai_client import OpenAIClient


class LLMClientModelValidationTests(unittest.TestCase):
    def assert_single_unknown_model_warning(self, warning_records, provider_name, model):
        self.assertEqual(len(warning_records), 1)
        self.assertIs(warning_records[0].category, UserWarning)
        self.assertIn(
            f"Unknown {provider_name} model '{model}'.",
            str(warning_records[0].message),
        )

    def test_client_warns_for_unknown_model(self):
        test_cases = [
            {
                "client_class": OpenAIClient,
                "patch_target": "tradingagents.llm_clients.openai_client.UnifiedChatOpenAI",
                "provider_name": "OpenAI",
                "model": "fake-openai-model",
                "kwargs": {},
            },
            {
                "client_class": AnthropicClient,
                "patch_target": "tradingagents.llm_clients.anthropic_client.ChatAnthropic",
                "provider_name": "Anthropic",
                "model": "fake-claude-model",
                "kwargs": {},
            },
            {
                "client_class": GoogleClient,
                "patch_target": "tradingagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI",
                "provider_name": "Google",
                "model": "fake-gemini-model",
                "kwargs": {},
            },
            {
                "client_class": OpenAIClient,
                "patch_target": "tradingagents.llm_clients.openai_client.UnifiedChatOpenAI",
                "provider_name": "opena",
                "model": "gpt-5-mini",
                "kwargs": {"provider": "opena"},
            },
        ]

        for case in test_cases:
            with self.subTest(provider=case["provider_name"]):
                with patch(case["patch_target"], side_effect=lambda **kwargs: kwargs):
                    with warnings.catch_warnings(record=True) as warning_records:
                        warnings.simplefilter("always")
                        llm = case["client_class"](case["model"], **case["kwargs"]).get_llm()

                self.assertEqual(llm["model"], case["model"])
                self.assert_single_unknown_model_warning(
                    warning_records, case["provider_name"], case["model"]
                )

    def test_openai_client_does_not_warn_for_known_model(self):
        with patch(
            "tradingagents.llm_clients.openai_client.UnifiedChatOpenAI",
            side_effect=lambda **kwargs: kwargs,
        ):
            with warnings.catch_warnings(record=True) as warning_records:
                warnings.simplefilter("always")
                llm = OpenAIClient("gpt-5-mini").get_llm()

        self.assertEqual(llm["model"], "gpt-5-mini")
        self.assertEqual(warning_records, [])

    def test_openrouter_allows_custom_model_without_warning(self):
        model = "custom-openrouter-model"

        with patch(
            "tradingagents.llm_clients.openai_client.UnifiedChatOpenAI",
            side_effect=lambda **kwargs: kwargs,
        ):
            with warnings.catch_warnings(record=True) as warning_records:
                warnings.simplefilter("always")
                llm = OpenAIClient(model, provider="openrouter").get_llm()

        self.assertEqual(llm["model"], model)
        self.assertEqual(llm["base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(warning_records, [])


if __name__ == "__main__":
    unittest.main()
