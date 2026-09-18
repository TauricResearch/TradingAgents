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


def test_legacy_ids_stay_valid_without_being_offered():
    from tradingagents.llm_clients.model_catalog import LEGACY_MODELS, MODEL_OPTIONS
    from tradingagents.llm_clients.validators import validate_model

    for provider, ids in LEGACY_MODELS.items():
        offered = {v for opts in MODEL_OPTIONS[provider].values() for _, v in opts}
        for model in ids:
            assert validate_model(provider, model), model
            assert model not in offered, f"{model} is legacy but still in the picker"


@pytest.mark.unit
def test_an_explicit_alias_of_a_listed_model_is_known():
    """gpt-5.6 is served under its own name and as gpt-5.6-sol; naming the
    explicit one should not warn that the model is unknown."""
    from tradingagents.llm_clients.validators import validate_model

    assert validate_model("openai", "gpt-5.6-sol")


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["openai", "anthropic", "google", "xai"])
@pytest.mark.parametrize("mode", ["quick", "deep"])
def test_every_provider_lets_you_name_your_own_model(provider, mode):
    """The docs tell users to name any model their provider serves; the picker
    has to offer that too, or a new model is unreachable until we ship a list."""
    from tradingagents.llm_clients.model_catalog import get_model_options

    assert "custom" in [value for _, value in get_model_options(provider, mode)]


@pytest.mark.unit
@pytest.mark.parametrize("provider, model", [
    ("xai", "grok-4.20-0309-reasoning"),
    ("deepseek", "deepseek-v4-flash"),
    ("qwen", "qwen3.7-max"),
])
def test_a_retired_model_id_still_runs_without_a_warning(provider, model):
    """A config written against an earlier release keeps working: the provider
    still serves these, they are just no longer offered in the picker."""
    from tradingagents.llm_clients.validators import validate_model

    assert validate_model(provider, model)
