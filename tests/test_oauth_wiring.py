"""Test wiring del provider openai-oauth: factory, env, validators, catalogo."""
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.openai_client import OpenAIClient
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.validators import validate_model
from tradingagents.llm_clients.model_catalog import get_model_options, get_known_models


def test_factory_dispatches_openai_oauth():
    client = create_llm_client("openai-oauth", "gpt-5.3-codex")
    assert isinstance(client, OpenAIClient)
    assert client.provider == "openai-oauth"


def test_openai_oauth_requires_no_env_key():
    assert get_api_key_env("openai-oauth") is None


def test_openai_oauth_validates_codex_models_only():
    assert validate_model("openai-oauth", "gpt-5.3-codex") is True
    assert validate_model("openai-oauth", "gpt-5.4") is True
    # Modelli generici NON-Codex sono rifiutati dal backend -> non validi qui
    assert validate_model("openai-oauth", "gpt-4.1") is False
    assert validate_model("openai-oauth", "gpt-5-mini") is False


def test_openai_oauth_catalog_is_codex_not_openai_alias():
    oauth_deep = {v for _, v in get_model_options("openai-oauth", "deep")}
    openai_deep = {v for _, v in get_model_options("openai", "deep")}
    assert "gpt-5.3-codex" in oauth_deep
    assert oauth_deep != openai_deep  # non è un alias
    # default deep raccomandato presente
    assert "gpt-5.3-codex" in {v for _, v in get_model_options("openai-oauth", "deep")}


def test_known_models_includes_oauth_catalog():
    known = get_known_models()
    assert "gpt-5.3-codex" in known["openai-oauth"]
