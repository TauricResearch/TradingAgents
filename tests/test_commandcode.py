"""Command Code protocol routing, credential isolation and real wire regressions.

All HTTP tests use a local mock transport. No key or billed inference is used.
"""

import asyncio
import json
import os
import sys
from types import SimpleNamespace

import pytest

from tradingagents.default_config import _apply_env_overrides
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.capabilities import get_capabilities
from tradingagents.llm_clients.commandcode import (
    COMMANDCODE_APIS,
    COMMANDCODE_BASE_URL,
    COMMANDCODE_MODEL_APIS,
    COMMANDCODE_MODEL_ENDPOINTS,
    CommandCodeClient,
    normalize_commandcode_model,
    resolve_commandcode_api,
    resolve_commandcode_base_url,
)
from tradingagents.llm_clients.factory import build_llm_kwargs, create_llm_client
from tradingagents.llm_clients.model_catalog import get_known_models, get_model_options


@pytest.fixture
def chat_spies(monkeypatch):
    def fake_type(kind):
        class FakeChat(SimpleNamespace):
            def __init__(self, **kwargs):
                super().__init__(kind=kind, kwargs=kwargs,
                                 root_client=SimpleNamespace(), root_async_client=SimpleNamespace(),
                                 _client=SimpleNamespace(), _async_client=SimpleNamespace())
        return FakeChat

    monkeypatch.setitem(sys.modules, "tradingagents.llm_clients.openai_client", SimpleNamespace(
        NormalizedChatOpenAI=fake_type("openai"),
        DeepSeekChatOpenAI=fake_type("deepseek"),
        _supports_reasoning_effort=lambda model: model.startswith("gpt-"),
    ))
    monkeypatch.setitem(sys.modules, "tradingagents.llm_clients.anthropic_client", SimpleNamespace(
        NormalizedChatAnthropic=fake_type("anthropic"),
        _supports_effort=lambda model: not model.startswith("claude-haiku-"),
    ))
    monkeypatch.setenv("CMD_API_KEY", "cmd-test-only-key")


@pytest.mark.parametrize("model,api", sorted(COMMANDCODE_MODEL_APIS.items()))
def test_every_known_model_uses_a_supported_protocol(model, api, chat_spies):
    client = create_llm_client("CommandCode", model)
    assert isinstance(client, CommandCodeClient)
    assert client.api == api
    assert api in COMMANDCODE_MODEL_ENDPOINTS[model]
    llm = client.get_llm()
    assert llm.kwargs["model"] == model
    assert llm.kwargs["api_key"] == "cmd-test-only-key"
    assert "api" not in llm.kwargs
    if api == "messages":
        assert llm.kind == "anthropic"
        assert llm.kwargs["base_url"] == "https://api.commandcode.ai/provider"
        assert "use_responses_api" not in llm.kwargs
    else:
        assert llm.kwargs["base_url"] == COMMANDCODE_BASE_URL
        assert llm.kwargs["use_responses_api"] is (api == "responses")
        expected = "deepseek" if model.startswith("deepseek/") else "openai"
        assert llm.kind == expected


def test_missing_key_never_uses_other_provider_keys(monkeypatch):
    monkeypatch.delenv("CMD_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "not-command-code")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "also-not-command-code")
    for model in ("gpt-6-luna", "claude-sonnet-5-5", "moonshotai/Kimi-K3"):
        with pytest.raises(ValueError, match="CMD_API_KEY"):
            CommandCodeClient(model).get_llm()


def test_explicit_key_overrides_environment(chat_spies):
    assert CommandCodeClient("gpt-6-luna", api_key="explicit").get_llm().kwargs["api_key"] == "explicit"


@pytest.mark.parametrize("model", [None, "", "  ", 123])
def test_empty_or_invalid_model_fails(model):
    with pytest.raises(ValueError, match="model ID"):
        normalize_commandcode_model(model)


def test_model_id_preserves_namespace_case_and_date_suffix():
    assert normalize_commandcode_model(" moonshotai/Kimi-K3 ") == "moonshotai/Kimi-K3"
    assert "claude-haiku-4-5-20251001" in COMMANDCODE_MODEL_APIS
    assert "claude-haiku-4-5" not in COMMANDCODE_MODEL_APIS


@pytest.mark.parametrize("api", sorted(COMMANDCODE_APIS))
def test_explicit_protocol_allows_future_models(api, chat_spies):
    client = CommandCodeClient("publisher/future-model", api=api)
    assert client.api == api
    assert client.validate_model()
    assert client.get_llm().kwargs["model"] == "publisher/future-model"


@pytest.mark.parametrize("model", ["future-model", "claude-future", "gpt-future"])
def test_unknown_model_requires_explicit_protocol(model):
    with pytest.raises(ValueError, match="TRADINGAGENTS_COMMANDCODE_API"):
        CommandCodeClient(model)


@pytest.mark.parametrize("api", [None, "", False, 123, "invalid"])
def test_invalid_protocol_fails(api):
    with pytest.raises(ValueError, match="commandcode_api"):
        resolve_commandcode_api("gpt-6-luna", api)


@pytest.mark.parametrize("model,api", [
    ("claude-sonnet-5-5", "responses"),
    ("claude-sonnet-5-5", "chat_completions"),
    ("gpt-6-luna", "messages"),
    ("Qwen/Qwen3.8-Flash", "responses"),
])
def test_known_unsupported_protocol_fails_before_request(model, api):
    with pytest.raises(ValueError, match="supports"):
        CommandCodeClient(model, api=api)


@pytest.mark.parametrize("api", ["responses", "chat_completions"])
def test_known_supported_protocol_can_be_overridden(api):
    assert CommandCodeClient("gpt-6-luna", api=api).api == api


@pytest.mark.parametrize("api,expected", [
    ("messages", "https://proxy.example/custom"),
    ("responses", "https://proxy.example/custom/v1"),
    ("chat_completions", "https://proxy.example/custom/v1"),
])
def test_proxy_url_is_preserved_without_duplicate_v1(api, expected):
    assert resolve_commandcode_base_url("https://proxy.example/custom/v1/", api) == expected


@pytest.mark.parametrize("url", [
    "not-a-url", "file:///tmp/api", "https://example.test/v1/messages/",
    "https://example.test/v1/responses", "https://example.test/v1/chat/completions",
    "https://user:password@example.test/v1", "https://example.test/v1?key=secret",
    "https://example.test/v1#fragment", "https://example.test/v1/models",
])
def test_invalid_base_url_fails(url):
    with pytest.raises(ValueError, match="backend_url"):
        resolve_commandcode_base_url(url, "messages")


def test_env_to_factory_and_common_settings(monkeypatch, chat_spies):
    monkeypatch.setenv("TRADINGAGENTS_COMMANDCODE_API", "responses")
    config = _apply_env_overrides({"llm_provider": "commandcode", "commandcode_api": "auto"})
    config.update(max_tokens="2048", llm_max_retries="3", temperature="0.2",
                  llm_headers={"x-cmd-zdr": "1"}, openai_reasoning_effort="high",
                  anthropic_effort="high")
    actual = create_llm_client("commandcode", "gpt-6-luna", **build_llm_kwargs(config)).get_llm().kwargs
    assert actual["max_tokens"] == 2048
    assert actual["max_retries"] == 3
    assert actual["temperature"] == 0.2
    assert actual["default_headers"] == {"x-cmd-zdr": "1"}
    assert actual["reasoning_effort"] == "high"
    assert "effort" not in actual


@pytest.mark.parametrize("model,expected", [("claude-sonnet-5-5", True), ("claude-haiku-4-5-20251001", False)])
def test_claude_effort_is_model_aware(model, expected, chat_spies):
    actual = CommandCodeClient(model, effort="high", reasoning_effort="high").get_llm().kwargs
    assert ("effort" in actual) is expected
    assert "reasoning_effort" not in actual


def test_headers_are_copied(chat_spies):
    headers = {"x-cmd-zdr": "1"}
    client = CommandCodeClient("gpt-6-luna", default_headers=headers)
    headers["x-cmd-zdr"] = "0"
    actual = client.get_llm().kwargs["default_headers"]
    actual["x-cmd-zdr"] = "0"
    assert client.get_llm().kwargs["default_headers"] == {"x-cmd-zdr": "1"}


def test_catalog_and_key_mapping():
    assert get_api_key_env("CommandCode") == "CMD_API_KEY"
    assert set(COMMANDCODE_MODEL_APIS) <= set(get_known_models()["commandcode"])
    for mode in ("quick", "deep"):
        options = get_model_options("commandcode", mode)
        assert ("Custom model ID", "custom") in options
        assert all(model in COMMANDCODE_MODEL_APIS or model == "custom" for _, model in options)


@pytest.mark.parametrize("model,native", [
    ("deepseek/deepseek-v4-flash", "deepseek-v4-flash"),
    ("MiniMaxAI/MiniMax-M3", "MiniMax-M3"),
    ("meta/muse-spark-1.3", "muse-spark-1.3"),
])
def test_official_namespaces_preserve_tool_capabilities(model, native):
    assert get_capabilities(model) == get_capabilities(native)


def test_protocol_prompt_skipped_for_known_mixed_models(monkeypatch):
    from cli import prompts
    monkeypatch.setattr(prompts.questionary, "select", lambda *a, **kw: pytest.fail("unexpected prompt"))
    assert prompts.ask_provider_api("commandcode", ["claude-sonnet-5-5", "gpt-6-luna"]) == "auto"
    assert prompts.provider_default_url("commandcode") == COMMANDCODE_BASE_URL


def test_protocol_prompt_limits_custom_model_to_compatible_shared_route(monkeypatch):
    from cli import prompts
    selections = []

    def select(*args, **kwargs):
        selections.extend(choice.value for choice in kwargs["choices"])
        return SimpleNamespace(ask=lambda: "messages")

    monkeypatch.setattr(prompts.questionary, "select", select)
    assert prompts.ask_provider_api("commandcode", ["future-model", "claude-sonnet-5-5"]) == "messages"
    assert selections == ["messages"]


def test_protocol_prompt_cancel_stops(monkeypatch):
    from cli import prompts
    monkeypatch.setattr(prompts.questionary, "select", lambda *a, **kw: SimpleNamespace(ask=lambda: None))
    with pytest.raises(SystemExit):
        prompts.ask_provider_api("commandcode", ["future-model"])


def _fake_response(model, api):
    if api == "messages":
        return {
            "id": "msg_test", "type": "message", "role": "assistant", "model": model,
            "content": [{"type": "text", "text": "OK"}], "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    if api == "responses":
        return {
            "id": "resp_test", "object": "response", "created_at": 1, "model": model,
            "status": "completed", "error": None, "incomplete_details": None,
            "output": [{"id": "msg_test", "type": "message", "role": "assistant",
                        "status": "completed", "content": [{
                            "type": "output_text", "text": "OK", "annotations": [],
                        }]}],
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }
    return {
        "id": "chatcmpl_test", "object": "chat.completion", "created": 1, "model": model,
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": "OK"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


@pytest.mark.parametrize("model", ["gpt-6-luna", "claude-sonnet-5-5", "deepseek/deepseek-v4-flash", "MiniMaxAI/MiniMax-M3"])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_real_sdk_wire_path_auth_headers_and_tools(model, asynchronous, monkeypatch):
    from langchain_core.messages import ChatMessage, HumanMessage

    try:
        from langchain_openai._compat import httpx
    except ImportError:
        import httpx

    monkeypatch.setenv("CMD_API_KEY", "cmd-test-only-key")
    # Foreign-provider settings must never override or accompany Command Code
    # credentials, on either SDK or on its asynchronous path.
    for prefix in ("OPENAI", "ANTHROPIC"):
        monkeypatch.setenv(f"{prefix}_CUSTOM_HEADERS", "Authorization: Bearer unrelated-token\nX-Private-Gateway: unrelated-private-value")
        monkeypatch.setenv(f"{prefix}_BASE_URL", "https://unrelated.example/v1")
        monkeypatch.setenv(f"{prefix}_PROXY", "http://unrelated-proxy.example:8080")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "unrelated-auth-token")
    monkeypatch.setenv("OPENAI_ORG_ID", "unrelated-org")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "unrelated-project")
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "unrelated-admin-key")
    original_environment = dict(os.environ)
    requests = []
    api = resolve_commandcode_api(model)

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=_fake_response(model, api))

    async def run():
        with httpx.Client(transport=httpx.MockTransport(handle)) as sync_client:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as async_client:
                llm = create_llm_client(
                    "commandcode", model, http_client=sync_client, http_async_client=async_client,
                    default_headers={"x-cmd-zdr": "1"}, max_retries=0, max_tokens=128,
                ).get_llm()
                bound = llm.bind_tools([{
                    "name": "get_price", "description": "Get a stock price", "parameters": {
                        "type": "object", "properties": {"ticker": {"type": "string"}},
                        "required": ["ticker"],
                    },
                }])
                prompt = ([ChatMessage(role="developer", content="Be concise"),
                           HumanMessage(content="Reply OK")]
                          if api == "chat_completions" else "Reply OK")
                if asynchronous:
                    await bound.ainvoke(prompt)
                else:
                    bound.invoke(prompt)

    asyncio.run(run())
    assert dict(os.environ) == original_environment
    assert len(requests) == 1
    request = requests[0]
    suffix = "chat/completions" if api == "chat_completions" else api
    assert request.url.path == f"/provider/v1/{suffix}"
    auth = request.headers.get("x-api-key") if api == "messages" else request.headers["authorization"]
    assert auth == ("cmd-test-only-key" if api == "messages" else "Bearer cmd-test-only-key")
    assert request.headers["x-cmd-zdr"] == "1"
    assert "x-private-gateway" not in request.headers
    assert "openai-organization" not in request.headers
    assert "openai-project" not in request.headers
    assert "unrelated" not in str(dict(request.headers))
    if api == "messages":
        assert "authorization" not in request.headers
    payload = json.loads(request.content)
    assert payload["model"] == model
    assert payload["tools"]
    assert "default_headers" not in payload
    assert "http_client" not in payload
    assert "http_async_client" not in payload
    assert "reasoning_split" not in payload  # No undocumented gateway extension.
    if api == "chat_completions":
        assert payload["max_tokens"] == 128
        assert "max_completion_tokens" not in payload
        assert payload["messages"][0]["role"] == "system"
