import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_factory_module(monkeypatch):
    package_name = "_lane4_factory_testpkg"
    package = ModuleType(package_name)
    package.__path__ = []
    monkeypatch.setitem(sys.modules, package_name, package)

    base_module = ModuleType(f"{package_name}.base_client")

    class BaseLLMClient:
        pass

    base_module.BaseLLMClient = BaseLLMClient
    monkeypatch.setitem(sys.modules, f"{package_name}.base_client", base_module)

    calls = []

    def _register_client(module_suffix: str, class_name: str):
        module = ModuleType(f"{package_name}.{module_suffix}")

        class Client:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs
                calls.append((class_name, args, kwargs))

        setattr(module, class_name, Client)
        monkeypatch.setitem(sys.modules, module.__name__, module)

    _register_client("openai_client", "OpenAIClient")
    _register_client("anthropic_client", "AnthropicClient")
    _register_client("google_client", "GoogleClient")

    factory_path = (
        Path(__file__).resolve().parents[2]
        / "tradingagents"
        / "llm_clients"
        / "factory.py"
    )
    spec = importlib.util.spec_from_file_location(f"{package_name}.factory", factory_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, calls


@pytest.mark.parametrize(
    ("provider", "expected_class", "expected_provider"),
    [
        ("openai", "OpenAIClient", "openai"),
        ("OpenRouter", "OpenAIClient", "openrouter"),
        ("ollama", "OpenAIClient", "ollama"),
        ("xai", "OpenAIClient", "xai"),
        ("anthropic", "AnthropicClient", None),
        ("google", "GoogleClient", None),
    ],
)
def test_create_llm_client_routes_provider_to_expected_adapter(
    monkeypatch,
    provider,
    expected_class,
    expected_provider,
):
    factory_module, calls = _load_factory_module(monkeypatch)

    client = factory_module.create_llm_client(
        provider=provider,
        model="demo-model",
        base_url="https://example.test",
        timeout=30,
    )

    assert client is not None
    assert calls[-1][0] == expected_class
    assert calls[-1][1] == ("demo-model", "https://example.test")
    if expected_provider is None:
        assert "provider" not in calls[-1][2]
    else:
        assert calls[-1][2]["provider"] == expected_provider
    assert calls[-1][2]["timeout"] == 30


def test_create_llm_client_rejects_unsupported_provider(monkeypatch):
    factory_module, _calls = _load_factory_module(monkeypatch)

    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        factory_module.create_llm_client("unknown", "demo-model")
