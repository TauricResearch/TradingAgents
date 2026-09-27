"""Go protocol, authentication, CLI registration and session regressions."""

import ast
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tradingagents.default_config import _apply_env_overrides
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.factory import build_llm_kwargs, create_llm_client
from tradingagents.llm_clients.model_catalog import get_known_models, get_model_options
from tradingagents.llm_clients.opencode_go import (
    GO_BASE_URL,
    GO_MODEL_APIS,
    OpenCodeGoClient,
    normalize_go_model,
    resolve_go_api,
    resolve_go_base_url,
)


@pytest.fixture
def chat_spies(monkeypatch):
    """Test adapter selection without installing SDKs or making API calls."""
    monkeypatch.setitem(sys.modules, "tradingagents.llm_clients.openai_client", SimpleNamespace(
        NormalizedChatOpenAI=lambda **kw: SimpleNamespace(kind="openai", kwargs=kw),
        DeepSeekChatOpenAI=lambda **kw: SimpleNamespace(kind="deepseek", kwargs=kw),
        _supports_reasoning_effort=lambda model: model.startswith("gpt-"),
    ))
    monkeypatch.setitem(sys.modules, "tradingagents.llm_clients.anthropic_client", SimpleNamespace(
        NormalizedChatAnthropic=lambda **kw: SimpleNamespace(kind="anthropic", kwargs=kw),
    ))
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "go-test-key")


@pytest.mark.parametrize("model,api", sorted(GO_MODEL_APIS.items()))
def test_every_known_model_routes_to_its_protocol(model, api, chat_spies):
    client = create_llm_client("opencode-go", model)
    llm = client.get_llm()
    assert client.api == api
    assert llm.kwargs["model"] == model
    assert llm.kwargs["api_key"] == "go-test-key"
    assert "api" not in llm.kwargs
    if api == "messages":
        assert llm.kind == "anthropic"
        assert llm.kwargs["base_url"] == "https://opencode.ai/zen/go"
        assert "use_responses_api" not in llm.kwargs
    else:
        assert llm.kind == ("deepseek" if model.startswith("deepseek-") else "openai")
        assert llm.kwargs["base_url"] == GO_BASE_URL
        assert llm.kwargs["use_responses_api"] is (api == "responses")


@pytest.mark.parametrize("model", ["glm-5.3-flash", "gpt-6-luna", "minimax-m3"])
def test_generated_sessions_stay_stable_and_separate(model, chat_spies):
    first = OpenCodeGoClient(model)
    a = first.get_llm().kwargs["default_headers"]
    b = first.get_llm().kwargs["default_headers"]
    c = OpenCodeGoClient(model).get_llm().kwargs["default_headers"]
    assert a == b
    assert a is not b
    assert a["x-opencode-session"] != c["x-opencode-session"]
    assert a["User-Agent"].startswith("TradingAgents/")


def test_custom_headers_override_defaults_case_insensitively(chat_spies):
    headers = {"USER-AGENT": "MyTradingAgents/test", "X-OPENCODE-SESSION": "resume-id", "X-Test": "yes"}
    config = {"llm_provider": "opencode-go", "llm_headers": headers}
    client = create_llm_client("opencode-go", "kimi-k3", **build_llm_kwargs(config))
    actual = client.get_llm().kwargs["default_headers"]
    assert actual == {"User-Agent": "MyTradingAgents/test", "x-opencode-session": "resume-id", "X-Test": "yes"}
    assert headers["X-OPENCODE-SESSION"] == "resume-id"
    headers["X-OPENCODE-SESSION"] = "changed-after-construction"
    assert client.get_llm().kwargs["default_headers"]["x-opencode-session"] == "resume-id"


@pytest.mark.parametrize("header", ["User-Agent", "x-opencode-session"])
def test_required_headers_cannot_be_empty(header):
    with pytest.raises(ValueError, match="nonempty"):
        OpenCodeGoClient("kimi-k3", default_headers={header: " "})


def test_go_key_is_required_without_falling_back_to_other_providers(monkeypatch):
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-go-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "also-not-a-go-key")
    with pytest.raises(ValueError, match="OPENCODE_GO_API_KEY"):
        OpenCodeGoClient("kimi-k3").get_llm()


def test_explicit_key_wins(chat_spies):
    assert OpenCodeGoClient("kimi-k3", api_key="explicit").get_llm().kwargs["api_key"] == "explicit"


@pytest.mark.parametrize("api", ["messages", "responses", "chat_completions"])
def test_explicit_protocol_supports_future_models(api, chat_spies):
    client = OpenCodeGoClient("future-model", api=api)
    assert client.validate_model()
    assert client.get_llm().kwargs["model"] == "future-model"


def test_unknown_auto_protocol_fails_instead_of_guessing():
    with pytest.raises(ValueError, match="TRADINGAGENTS_OPENCODE_GO_API"):
        OpenCodeGoClient("future-model")


@pytest.mark.parametrize("api", ["invalid", "", None, False, 123])
def test_invalid_protocol_is_rejected(api):
    with pytest.raises(ValueError, match="opencode_go_api"):
        resolve_go_api("kimi-k3", api)


@pytest.mark.parametrize("model", [None, "", " ", "opencode-go/"])
def test_empty_model_is_rejected(model):
    with pytest.raises(ValueError, match="model ID"):
        normalize_go_model(model)


def test_prefixed_and_native_provider_style_ids_are_normalized():
    assert normalize_go_model("opencode-go/kimi-k3") == "kimi-k3"
    assert normalize_go_model("MiniMax-M3") == "minimax-m3"
    assert resolve_go_api("opencode-go/minimax-m3") == "messages"


@pytest.mark.parametrize("api,expected", [
    ("messages", "https://proxy.example/custom"),
    ("responses", "https://proxy.example/custom/v1"),
    ("chat_completions", "https://proxy.example/custom/v1"),
])
def test_proxy_base_url_is_preserved_and_v1_not_duplicated(api, expected):
    assert resolve_go_base_url("https://proxy.example/custom/v1/", api) == expected


@pytest.mark.parametrize("url", [
    "not-a-url", "file:///tmp/go", "https://example.test/v1/messages",
    "https://example.test/v1/responses", "https://example.test/v1/chat/completions",
    "https://user:password@example.test/v1", "https://example.test/v1?key=secret",
    "https://example.test/v1#fragment",
])
def test_bad_base_urls_fail(url):
    with pytest.raises(ValueError, match="backend_url"):
        resolve_go_base_url(url, "messages")


def test_env_factory_and_standard_options(chat_spies, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_OPENCODE_GO_API", "responses")
    config = _apply_env_overrides({"llm_provider": "opencode-go", "opencode_go_api": "auto"})
    config.update(temperature=0.2, max_tokens=1024, llm_max_retries=4,
                  openai_reasoning_effort="high")
    client = create_llm_client("opencode-go", "gpt-6-luna", **build_llm_kwargs(config))
    kwargs = client.get_llm().kwargs
    assert kwargs["use_responses_api"] is True
    assert kwargs["max_tokens"] == 1024
    assert kwargs["max_retries"] == 4
    assert kwargs["temperature"] == 0.2
    assert kwargs["reasoning_effort"] == "high"


@pytest.mark.parametrize("model", ["grok-4.7", "glm-5.3-flash", "minimax-m3"])
def test_openai_reasoning_effort_is_not_sent_to_other_models(model, chat_spies):
    assert "reasoning_effort" not in OpenCodeGoClient(model, reasoning_effort="high").get_llm().kwargs


def test_catalog_and_key_mapping():
    assert get_api_key_env("OpenCode-Go") == "OPENCODE_GO_API_KEY"
    assert set(GO_MODEL_APIS) <= set(get_known_models()["opencode-go"])
    for mode in ("quick", "deep"):
        options = get_model_options("opencode-go", mode)
        assert ("Custom model ID", "custom") in options
        assert all(model in GO_MODEL_APIS or model == "custom" for _, model in options)


def test_cli_provider_table_and_url_resolution_without_starting_ui():
    # These pure functions need no terminal/SDK dependencies. Execute their
    # actual AST bodies rather than importing the full interactive application.
    path = Path(__file__).parents[1] / "cli" / "prompts.py"
    parsed = ast.parse(path.read_text(encoding="utf-8"))
    names = {"_llm_provider_table", "provider_default_url", "resolve_backend_url"}
    nodes = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {"os": os, "GO_BASE_URL": GO_BASE_URL}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    assert ("OpenCode Go", "opencode-go", GO_BASE_URL) in namespace["_llm_provider_table"]()
    assert namespace["provider_default_url"]("opencode-go") == GO_BASE_URL
    assert namespace["resolve_backend_url"]("opencode-go", env_url="https://proxy.test/v1") == "https://proxy.test/v1"


@pytest.mark.parametrize("model", ["glm-5.3-flash", "gpt-6-luna", "minimax-m3"])
def test_real_sdk_clients_receive_headers_on_sync_and_async_paths(model, monkeypatch):
    pytest.importorskip("langchain_openai")
    pytest.importorskip("langchain_anthropic")
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "go-test-key")
    llm = OpenCodeGoClient(model, default_headers={"x-opencode-session": "stable-test"}).get_llm()
    if resolve_go_api(model) == "messages":
        clients = (llm._client, llm._async_client)
    else:
        clients = (llm.root_client, llm.root_async_client)
    for client in clients:
        headers = {k.lower(): v for k, v in client.default_headers.items()}
        assert headers["x-opencode-session"] == "stable-test"
        assert headers["user-agent"].startswith("TradingAgents/")
