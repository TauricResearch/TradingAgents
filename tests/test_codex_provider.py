"""The openai_codex provider targets the ChatGPT-subscription Codex endpoint.

That endpoint rejects `stream: false`, `store: true`, `temperature`, and any
input item carrying the `system` role (all HTTP 400), and authenticates from the
Codex client's auth file rather than an env var. These tests pin each of those so
a future registry edit can't silently produce a client that 400s on its first
call.
"""
from __future__ import annotations

import dataclasses

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients import codex_auth
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.openai_client import (
    OPENAI_COMPATIBLE_PROVIDERS,
    CodexChatOpenAI,
    OpenAIClient,
    _supports_temperature,
    is_openai_compatible,
)

CREDENTIALS = codex_auth.CodexCredentials(token="tok-abc", account_id="acct-123")


def _patch_credentials_fn(monkeypatch, fn):
    """Swap the registry's credential hook.

    The registry captured ``codex_auth.resolve`` by reference at import time, so
    monkeypatching the module attribute would not reach it — the spec row itself
    has to be replaced.
    """
    spec = OPENAI_COMPATIBLE_PROVIDERS["openai_codex"]
    monkeypatch.setitem(
        OPENAI_COMPATIBLE_PROVIDERS,
        "openai_codex",
        dataclasses.replace(spec, credentials_fn=fn),
    )


@pytest.fixture()
def stub_credentials(monkeypatch):
    _patch_credentials_fn(monkeypatch, lambda: CREDENTIALS)


@pytest.mark.unit
def test_provider_is_registered():
    assert is_openai_compatible("openai_codex")
    spec = OPENAI_COMPATIBLE_PROVIDERS["openai_codex"]
    assert spec.base_url == "https://chatgpt.com/backend-api/codex"
    assert spec.chat_class is CodexChatOpenAI
    assert spec.use_responses_api is True
    assert spec.forces_responses_api is True
    assert spec.credentials_fn is codex_auth.resolve


@pytest.mark.unit
def test_no_api_key_env_var():
    # Authenticates from the Codex auth file, like bedrock's credential chain.
    assert get_api_key_env("openai_codex") is None


@pytest.mark.unit
def test_client_is_built_from_the_resolved_credentials(stub_credentials):
    llm = create_llm_client("openai_codex", "gpt-5.5").get_llm()

    assert isinstance(llm, CodexChatOpenAI)
    assert llm.default_headers["chatgpt-account-id"] == "acct-123"
    assert llm.use_responses_api is True
    assert llm.streaming is True
    assert llm.store is False


@pytest.mark.unit
def test_streaming_dispatch_matches_the_payload(stub_credentials):
    # langchain takes `stream` for the payload from the attribute but decides
    # which code path to run from model_fields_set. A class-level field default
    # satisfies the first and not the second, so the request says stream:true
    # and the SSE reply is then handed to the non-streaming parser
    # ("'Stream' object has no attribute 'error'"). Asserting llm.streaming is
    # True does not catch that; asserting the two agree does.
    llm = create_llm_client("openai_codex", "gpt-5.4-mini").get_llm()
    assert llm._should_stream(async_api=False) is True
    assert llm._get_request_payload([("user", "hi")])["stream"] is True


@pytest.mark.unit
def test_system_messages_are_sent_as_developer(stub_credentials):
    # Every agent prompt is a ChatPromptTemplate whose first message is a system
    # message, and the endpoint answers any input item with role "system" with
    # 400 "System messages are not allowed" — even when `instructions` is also
    # set. "developer" is the Responses-API name for the same role and is
    # accepted, so the rewrite must happen before the request leaves.
    llm = create_llm_client("openai_codex", "gpt-5.4-mini").get_llm()

    payload = llm._get_request_payload(
        [SystemMessage("be terse"), HumanMessage("hi"), AIMessage("yo")]
    )

    roles = [item["role"] for item in payload["input"] if "role" in item]
    assert roles == ["developer", "user", "assistant"]
    assert payload["input"][0]["content"] == "be terse"


@pytest.mark.unit
def test_system_messages_survive_untouched_on_native_openai(monkeypatch):
    # The rewrite is a Codex-endpoint workaround, not a repo-wide policy: native
    # OpenAI accepts (and bills prompt-cache hits on) the system role.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    llm = OpenAIClient("gpt-5.4-mini", provider="openai").get_llm()

    payload = llm._get_request_payload([SystemMessage("be terse"), HumanMessage("hi")])

    assert [item["role"] for item in payload["input"] if "role" in item] == [
        "system",
        "user",
    ]


@pytest.mark.unit
def test_responses_api_survives_the_non_openai_host(stub_credentials):
    # The #1024 hostname guard would otherwise downgrade chatgpt.com to Chat
    # Completions, which this endpoint does not serve.
    llm = OpenAIClient("gpt-5.5", provider="openai_codex").get_llm()
    assert llm.use_responses_api is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "provider,expected", [("openai_codex", False), ("openai", True), ("xai", True)]
)
def test_temperature_support_by_provider(provider, expected):
    assert _supports_temperature(provider) is expected


@pytest.mark.unit
def test_temperature_is_dropped_for_codex_only(stub_credentials, monkeypatch):
    # gpt-4.1, not a gpt-5 ID: langchain_openai nulls temperature itself for the
    # gpt-5/o-series, which would mask whether the drop was ours. With a model
    # langchain does forward, the only difference between the two arms is the
    # provider — which is exactly what this test is about.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    codex = OpenAIClient("gpt-4.1", provider="openai_codex", temperature=0.3).get_llm()
    openai = OpenAIClient("gpt-4.1", provider="openai", temperature=0.3).get_llm()

    # Asserting "not 0.3" rather than "is None" keeps this independent of
    # whatever ChatOpenAI uses as its own unset default.
    assert codex.temperature != 0.3
    assert openai.temperature == 0.3


@pytest.mark.unit
def test_max_retries_still_reaches_the_client(stub_credentials):
    # The retry budget stays the cross-provider llm_max_retries knob (#1091);
    # nothing Codex-specific may shadow it.
    llm = OpenAIClient("gpt-5.5", provider="openai_codex", max_retries=7).get_llm()
    assert llm.max_retries == 7


@pytest.mark.unit
def test_auth_failure_propagates(monkeypatch):
    def _fail():
        raise codex_auth.CodexAuthError("no credentials")

    _patch_credentials_fn(monkeypatch, _fail)
    with pytest.raises(codex_auth.CodexAuthError):
        OpenAIClient("gpt-5.5", provider="openai_codex").get_llm()


# --- reasoning effort forwarding -------------------------------------------


def _bare_graph(config: dict) -> TradingAgentsGraph:
    """A graph shell with only the config attribute the method under test reads."""
    graph = object.__new__(TradingAgentsGraph)
    graph.config = config
    return graph


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["openai", "openai_codex"])
def test_reasoning_effort_is_forwarded(provider):
    # _get_provider_kwargs dispatches on an exact provider name, so a new key
    # silently receives nothing unless it is added to the branch.
    kwargs = _bare_graph(
        {"llm_provider": provider, "openai_reasoning_effort": "high"}
    )._get_provider_kwargs()
    assert kwargs["reasoning_effort"] == "high"


@pytest.mark.unit
def test_reasoning_effort_absent_when_unset():
    kwargs = _bare_graph(
        {"llm_provider": "openai_codex", "openai_reasoning_effort": None}
    )._get_provider_kwargs()
    assert "reasoning_effort" not in kwargs
