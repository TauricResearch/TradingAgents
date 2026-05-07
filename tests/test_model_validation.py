import unittest
import warnings

import pytest

from tradingagents.llm_clients.base_client import BaseLLMClient
from tradingagents.llm_clients.model_catalog import get_known_models
from tradingagents.llm_clients.validators import validate_model


class DummyLLMClient(BaseLLMClient):
    def __init__(self, provider: str, model: str):
        self.provider = provider
        super().__init__(model)

    def get_llm(self):
        self.warn_if_unknown_model()
        return object()

    def validate_model(self) -> bool:
        return validate_model(self.provider, self.model)


@pytest.mark.unit
class ModelValidationTests(unittest.TestCase):
    def test_cli_catalog_models_are_all_validator_approved(self):
        for provider, models in get_known_models().items():
            if provider in ("ollama", "openrouter"):
                continue

            for model in models:
                with self.subTest(provider=provider, model=model):
                    self.assertTrue(validate_model(provider, model))

    def test_unknown_model_emits_warning_for_strict_provider(self):
        client = DummyLLMClient("openai", "not-a-real-openai-model")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client.get_llm()

        self.assertEqual(len(caught), 1)
        self.assertIn("not-a-real-openai-model", str(caught[0].message))
        self.assertIn("openai", str(caught[0].message))

    def test_openrouter_and_ollama_accept_custom_models_without_warning(self):
        for provider in ("openrouter", "ollama"):
            client = DummyLLMClient(provider, "custom-model-name")

            with self.subTest(provider=provider):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    client.get_llm()

                self.assertEqual(caught, [])


def test_openai_with_custom_base_url_accepts_unknown_model_without_warning():
    from tradingagents.llm_clients.openai_client import OpenAIClient

    client = OpenAIClient(
        "mercury",
        base_url="https://api.inceptionlabs.ai/v1",
        provider="openai",
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert client.validate_model() is True
        client.warn_if_unknown_model()

    assert caught == []


def test_openai_custom_base_url_does_not_force_responses_api(monkeypatch):
    from tradingagents.llm_clients import openai_client

    captured = {}

    class FakeChat:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(openai_client, "NormalizedChatOpenAI", FakeChat)

    client = openai_client.OpenAIClient(
        "mercury",
        base_url="https://api.inceptionlabs.ai/v1",
        provider="openai",
    )
    client.get_llm()

    assert captured["model"] == "mercury"
    assert captured["base_url"] == "https://api.inceptionlabs.ai/v1"
    assert "use_responses_api" not in captured


def test_openai_custom_base_url_does_not_forward_reasoning_effort(monkeypatch):
    from tradingagents.llm_clients import openai_client

    captured = {}

    class FakeChat:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(openai_client, "NormalizedChatOpenAI", FakeChat)

    client = openai_client.OpenAIClient(
        "mercury",
        base_url="https://api.inceptionlabs.ai/v1",
        provider="openai",
        reasoning_effort="high",
    )
    client.get_llm()

    assert "reasoning_effort" not in captured


def test_openai_default_base_url_is_native_openai(monkeypatch):
    from tradingagents.llm_clients import openai_client

    captured = {}

    class FakeChat:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(openai_client, "NormalizedChatOpenAI", FakeChat)

    client = openai_client.OpenAIClient(
        "gpt-5.4-mini",
        base_url="https://api.openai.com/v1",
        provider="openai",
    )
    client.get_llm()

    assert "base_url" not in captured
    assert captured["use_responses_api"] is True
