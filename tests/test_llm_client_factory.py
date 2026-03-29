import unittest
import warnings

from tradingagents.llm_clients.factory import create_llm_client


class LLMClientFactoryTests(unittest.TestCase):
    def test_invalid_known_provider_model_emits_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client = create_llm_client("openai", "not-a-real-openai-model")

        self.assertEqual(client.provider, "openai")
        self.assertTrue(
            any("not-a-real-openai-model" in str(w.message) for w in caught)
        )

    def test_known_valid_model_does_not_emit_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client = create_llm_client("openai", "gpt-5-mini")

        self.assertEqual(client.provider, "openai")
        self.assertEqual(len(caught), 0)

    def test_ollama_custom_models_do_not_emit_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client = create_llm_client("ollama", "qwen3:8b")

        self.assertEqual(client.provider, "ollama")
        self.assertEqual(len(caught), 0)


if __name__ == "__main__":
    unittest.main()
