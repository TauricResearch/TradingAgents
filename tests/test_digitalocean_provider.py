"""DigitalOcean Gradient serverless inference as an OpenAI-compatible provider."""

import pytest

from cli.prompts import provider_default_url
from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS
from tradingagents.llm_clients.validators import validate_model

pytestmark = pytest.mark.unit

ENDPOINT = "https://inference.do-ai.run/v1"
KEY_ENV = "DIGITALOCEAN_MODEL_ACCESS_KEY"


def test_the_provider_is_in_the_openai_compatible_registry():
    assert "digitalocean" in OPENAI_COMPATIBLE_PROVIDERS


def test_the_endpoint_is_digitaloceans_inference_url():
    assert OPENAI_COMPATIBLE_PROVIDERS["digitalocean"].base_url == ENDPOINT
    assert provider_default_url("digitalocean") == ENDPOINT


def test_the_key_env_var_is_registered(monkeypatch):
    """Registering it here is what makes the CLI prompt for the key."""
    assert get_api_key_env("digitalocean") == KEY_ENV


def test_a_client_points_at_the_endpoint_with_the_key(monkeypatch):
    monkeypatch.setenv(KEY_ENV, "do-test-key")
    llm = create_llm_client("digitalocean", "anthropic-claude-opus-5.5").get_llm()

    assert str(llm.openai_api_base) == ENDPOINT
    assert llm.openai_api_key.get_secret_value() == "do-test-key"
    assert llm.model_name == "anthropic-claude-opus-5.5"


def test_a_missing_key_fails_with_the_variable_to_set(monkeypatch):
    """The key is required: DO's endpoint authenticates every request."""
    monkeypatch.delenv(KEY_ENV, raising=False)
    with pytest.raises(ValueError, match=KEY_ENV):
        create_llm_client("digitalocean", "openai-gpt-6-sol").get_llm()


def test_the_responses_api_is_not_used(monkeypatch):
    """/v1/responses is native OpenAI only; DO speaks chat completions."""
    monkeypatch.setenv(KEY_ENV, "do-test-key")
    llm = create_llm_client("digitalocean", "openai-gpt-6-sol").get_llm()
    # Left unset rather than set to False, which langchain reads the same way.
    assert not getattr(llm, "use_responses_api", False)


def test_the_endpoint_can_be_overridden(monkeypatch):
    """For a DO region or a gateway in front of it."""
    monkeypatch.setenv(KEY_ENV, "do-test-key")
    monkeypatch.setenv("DIGITALOCEAN_INFERENCE_URL", "https://gateway.internal/v1")
    llm = create_llm_client("digitalocean", "openai-gpt-6-sol").get_llm()
    assert str(llm.openai_api_base) == "https://gateway.internal/v1"


def test_an_explicit_base_url_still_wins_over_the_env(monkeypatch):
    monkeypatch.setenv(KEY_ENV, "do-test-key")
    monkeypatch.setenv("DIGITALOCEAN_INFERENCE_URL", "https://gateway.internal/v1")
    llm = create_llm_client("digitalocean", "openai-gpt-6-sol",
                            base_url="https://explicit/v1").get_llm()
    assert str(llm.openai_api_base) == "https://explicit/v1"


def test_the_catalog_offers_both_modes():
    for mode in ("quick", "deep"):
        options = get_model_options("digitalocean", mode)
        assert options
        assert options[-1] == ("Custom model ID", "custom")


def test_the_catalog_uses_digitaloceans_namespaced_ids():
    """DO namespaces by vendor: Anthropic's own ID would 404 against this endpoint."""
    deep = {value: label for label, value in get_model_options("digitalocean", "deep")}

    assert "anthropic-claude-opus-5.5" in deep
    assert "claude-opus-5-5" not in deep


def test_any_model_id_is_accepted():
    """DO's catalog turns over with every model release, so none is rejected."""
    assert validate_model("digitalocean", "some-model-do-added-last-week")
