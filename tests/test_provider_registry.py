"""The OpenAI-compatible provider registry is the single source of truth for the
family; this guards each provider's resolved config (base URL, subclass, auth,
Responses API) so a future edit can't silently break one.
"""
import pytest

from tradingagents.llm_clients.openai_client import (
    OPENAI_COMPATIBLE_PROVIDERS,
    DeepSeekChatOpenAI,
    LocalCompatibleChatOpenAI,
    MinimaxChatOpenAI,
    NormalizedChatOpenAI,
    is_openai_compatible,
)


@pytest.mark.unit
def test_registry_membership():
    assert is_openai_compatible("openai")
    assert is_openai_compatible("openai_compatible")  # the generic endpoint
    # native (different API) clients are intentionally NOT in the registry
    assert not is_openai_compatible("anthropic")
    assert not is_openai_compatible("google")
    assert not is_openai_compatible("azure")


@pytest.mark.unit
@pytest.mark.parametrize("provider,base_url,chat_class,responses", [
    ("openai", None, NormalizedChatOpenAI, True),
    ("xai", "https://api.x.ai/v1", NormalizedChatOpenAI, False),
    ("deepseek", "https://api.deepseek.com", DeepSeekChatOpenAI, False),
    ("qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", NormalizedChatOpenAI, False),
    ("qwen-cn", "https://dashscope.aliyuncs.com/compatible-mode/v1", NormalizedChatOpenAI, False),
    ("glm", "https://api.z.ai/api/paas/v4/", NormalizedChatOpenAI, False),
    ("glm-cn", "https://open.bigmodel.cn/api/paas/v4/", NormalizedChatOpenAI, False),
    ("minimax", "https://api.minimax.io/v1", MinimaxChatOpenAI, False),
    ("minimax-cn", "https://api.minimaxi.com/v1", MinimaxChatOpenAI, False),
    ("openrouter", "https://openrouter.ai/api/v1", NormalizedChatOpenAI, False),
    ("mistral", "https://api.mistral.ai/v1", NormalizedChatOpenAI, False),
    ("kimi", "https://api.moonshot.ai/v1", NormalizedChatOpenAI, False),
    ("groq", "https://api.groq.com/openai/v1", NormalizedChatOpenAI, False),
    ("nvidia", "https://integrate.api.nvidia.com/v1", NormalizedChatOpenAI, False),
    ("ollama", "http://localhost:11434/v1", LocalCompatibleChatOpenAI, False),
])
def test_registry_spec(provider, base_url, chat_class, responses):
    spec = OPENAI_COMPATIBLE_PROVIDERS[provider]
    assert spec.base_url == base_url
    assert spec.chat_class is chat_class
    assert spec.use_responses_api is responses


@pytest.mark.unit
def test_key_optionality():
    # Local/generic endpoints are key-optional; hosted APIs require a key.
    assert OPENAI_COMPATIBLE_PROVIDERS["ollama"].key_optional is True
    assert OPENAI_COMPATIBLE_PROVIDERS["openai_compatible"].key_optional is True
    assert OPENAI_COMPATIBLE_PROVIDERS["openai_compatible"].require_base_url is True
    assert OPENAI_COMPATIBLE_PROVIDERS["xai"].key_optional is False
    # OLLAMA_BASE_URL is the only base-URL env override.
    assert OPENAI_COMPATIBLE_PROVIDERS["ollama"].base_url_env == "OLLAMA_BASE_URL"


# --- a provider that signs in: its own credential, its own pinned endpoint ---------

class _Recorder:
    """Stands in for the chat class and records what the client built."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _signed_in_provider(monkeypatch, token="plan-token"):
    from tradingagents.llm_clients import openai_client

    spec = openai_client.ProviderSpec(
        base_url="https://api.openai.com/v1", pinned_base_url=True, use_responses_api=True,
        credential=lambda: (lambda: token), chat_class=_Recorder,
    )
    monkeypatch.setitem(openai_client.OPENAI_COMPATIBLE_PROVIDERS, "signed-in", spec)
    return openai_client


@pytest.mark.unit
def test_a_signed_in_provider_sends_its_own_credential_never_an_api_key(monkeypatch):
    openai_client = _signed_in_provider(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-be-used")
    llm = openai_client.OpenAIClient("gpt-x", provider="signed-in").get_llm()
    assert callable(llm.kwargs["api_key"]) and llm.kwargs["api_key"]() == "plan-token"
    assert llm.kwargs["base_url"] == "https://api.openai.com/v1"


@pytest.mark.unit
@pytest.mark.parametrize("client_kwargs", [
    {"base_url": "https://relay.example/v1"},       # backend_url / TRADINGAGENTS_LLM_BACKEND_URL
    {"api_key": "sk-explicit"},
])
def test_a_signed_in_provider_refuses_another_endpoint_or_key(monkeypatch, client_kwargs):
    openai_client = _signed_in_provider(monkeypatch)
    base_url = client_kwargs.pop("base_url", None)
    client = openai_client.OpenAIClient("gpt-x", base_url=base_url, provider="signed-in", **client_kwargs)
    with pytest.raises(ValueError):
        client.get_llm()


@pytest.mark.unit
def test_a_missing_sign_in_fails_before_any_request(monkeypatch):
    from tradingagents.llm_clients import openai_client

    def not_signed_in():
        raise ValueError("Not signed in; run `tradingagents login chatgpt`.")

    spec = openai_client.ProviderSpec(base_url="https://api.openai.com/v1", pinned_base_url=True,
                                      credential=not_signed_in, chat_class=_Recorder)
    monkeypatch.setitem(openai_client.OPENAI_COMPATIBLE_PROVIDERS, "signed-in", spec)
    with pytest.raises(ValueError, match="login chatgpt"):
        openai_client.OpenAIClient("gpt-x", provider="signed-in").get_llm()
