"""Custom-header configuration and SDK transport regression tests."""

import asyncio
import json
from dataclasses import replace

import pytest

from tradingagents.default_config import _apply_env_overrides
from tradingagents.llm_clients.factory import build_llm_kwargs, create_llm_client
from tradingagents.llm_clients.headers import parse_llm_headers


@pytest.mark.parametrize("value", [None, "", {}, "{}"])
def test_empty_headers(value):
    assert parse_llm_headers(value) == {}
    assert "default_headers" not in build_llm_kwargs({"llm_headers": value})


@pytest.mark.parametrize("value", [{"X-Test": "yes"}, '{"X-Test":"yes"}'])
def test_headers_are_copied_and_forwarded(value):
    result = build_llm_kwargs({"llm_provider": "openai_compatible", "llm_headers": value})
    assert result["default_headers"] == {"X-Test": "yes"}
    assert result["default_headers"] is not value


@pytest.mark.parametrize("value", [
    "not-json", "[]", "null", "true", "42", [], True,
    {"": "a"}, {"Bad Name": "a"}, {"X-Test": 5}, {1: "a"},
    {"X-Test": "a\r\nb"}, {"X-Test": "a\x00b"}, {"X-Test": "é"},
    {"X-Test": "a", "x-test": "b"}, '{"X-Test":"a","X-Test":"b"}',
])
def test_invalid_headers_fail(value):
    with pytest.raises(ValueError, match="llm_headers"):
        parse_llm_headers(value)


def test_validation_does_not_expose_header_values():
    secret = "a-real-secret"
    for value in ['{"X-Key":"' + secret, {"X-Key": secret + "\n"}]:
        with pytest.raises(ValueError) as caught:
            parse_llm_headers(value)
        assert secret not in str(caught.value)


def test_env_to_factory(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_LLM_HEADERS", '{"X-Test":"from-env"}')
    config = _apply_env_overrides({"llm_provider": "openai", "llm_headers": None})
    assert build_llm_kwargs(config)["default_headers"] == {"X-Test": "from-env"}
    config["llm_headers"] = {"X-Test": "explicit"}
    assert build_llm_kwargs(config)["default_headers"] == {"X-Test": "explicit"}


@pytest.mark.parametrize("provider", ["google", "bedrock"])
def test_unsupported_adapters_do_not_silently_drop_headers(provider):
    with pytest.raises(ValueError, match="not supported"):
        build_llm_kwargs({"llm_provider": provider, "llm_headers": {"X-Test": "yes"}})


@pytest.mark.parametrize("provider", ["openai_compatible", "anthropic", "azure"])
def test_client_constructor_receives_headers(provider, monkeypatch):
    if provider == "anthropic":
        pytest.importorskip("langchain_anthropic")
        from tradingagents.llm_clients import anthropic_client as module
        target = "NormalizedChatAnthropic"
    else:
        pytest.importorskip("langchain_openai")
        if provider == "azure":
            from tradingagents.llm_clients import azure_client as module
            target = "NormalizedAzureChatOpenAI"
        else:
            from tradingagents.llm_clients import openai_client as module
            spec = module.OPENAI_COMPATIBLE_PROVIDERS[provider]
            monkeypatch.setitem(module.OPENAI_COMPATIBLE_PROVIDERS, provider,
                                replace(spec, chat_class=lambda **kw: kw))
            target = None
    if target:
        monkeypatch.setattr(module, target, lambda **kw: kw)
    headers = {"X-Test": "yes"}
    client = create_llm_client(provider, "custom", base_url="https://example.test/v1",
                               **build_llm_kwargs({"llm_provider": provider, "llm_headers": headers}))
    assert client.get_llm()["default_headers"] == headers


@pytest.mark.parametrize("asynchronous", [False, True])
def test_openai_headers_reach_http_not_request_body(asynchronous):
    pytest.importorskip("langchain_openai")
    try:
        from langchain_openai._compat import httpx
    except ImportError:
        import httpx

    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "chatcmpl-test", "object": "chat.completion", "created": 0,
            "model": "custom", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": "OK"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    async def run():
        with httpx.Client(transport=httpx.MockTransport(handle)) as sync_client:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as async_client:
                llm = create_llm_client(
                    "openai_compatible", "custom", base_url="https://example.test/v1",
                    http_client=sync_client, http_async_client=async_client,
                    **build_llm_kwargs({"llm_provider": "openai_compatible", "llm_headers": {
                        "User-Agent": "TradingAgents/test", "X-Test": "wire-value",
                    }}),
                ).get_llm()
                if asynchronous:
                    await llm.ainvoke("Reply OK")
                else:
                    llm.invoke("Reply OK")

    asyncio.run(run())
    assert len(requests) == 1
    assert requests[0].headers["user-agent"] == "TradingAgents/test"
    assert requests[0].headers["x-test"] == "wire-value"
    assert "default_headers" not in json.loads(requests[0].content)
    assert "llm_headers" not in json.loads(requests[0].content)
