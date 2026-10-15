"""OpenAI ``reasoning_effort`` is gated to reasoning models.

Non-reasoning OpenAI models (gpt-4.1, gpt-4o, ...) 400 with "Unsupported
parameter: 'reasoning.effort'". The client must drop the kwarg for those rather
than forward it and crash the run. The GPT-5 family and the o-series accept it.
"""

import pytest

from tradingagents.llm_clients.openai_client import (
    OpenAIClient,
    _supports_reasoning_effort,
)


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-5.5", True), ("gpt-5.4", True), ("gpt-5.4-mini", True),
        ("gpt-5.5-pro", True), ("gpt-6-astra", True), ("o1", True), ("o3-mini", True),
        ("gpt-4.1", False), ("gpt-4o", False), ("gpt-4o-mini", False),
        ("gpt-3.5-turbo", False), ("gpt-10", True),
        ("gpt-5foo", False), ("gpt-60x", False), ("o3rd-party", False),
    ],
)
def test_supports_reasoning_effort(model, expected):
    assert _supports_reasoning_effort(model) is expected


def _effort_on(model, monkeypatch):
    # A fake key lets get_llm() construct the client without a network call.
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    llm = OpenAIClient(model, provider="openai", reasoning_effort="low").get_llm()
    return getattr(llm, "reasoning_effort", None)


def test_reasoning_model_receives_effort(monkeypatch):
    assert _effort_on("gpt-5.4-mini", monkeypatch) == "low"


def test_non_reasoning_model_drops_effort(monkeypatch):
    # gpt-4.1 would 400 with reasoning_effort — it must be dropped.
    assert _effort_on("gpt-4.1", monkeypatch) is None


def test_compatible_server_keeps_effort_for_non_openai_model_names():
    # LM Studio accepts reasoning_effort for thinking models even though the
    # model id is not a GPT-5/o-series name — it must reach the client, not be
    # dropped by the native-OpenAI model gate.
    llm = OpenAIClient(
        "unsloth/qwen3.8-27b", base_url="http://localhost:1234/v1",
        provider="openai_compatible", reasoning_effort="high",
    ).get_llm()
    assert getattr(llm, "reasoning_effort", None) == "high"


def test_factory_forwards_reasoning_effort_to_openai_compatible():
    from tradingagents import default_config
    from tradingagents.llm_clients import factory

    config = {**default_config.DEFAULT_CONFIG, "llm_provider": "openai_compatible",
              "backend_url": "http://localhost:1234/v1",
              "quick_think_llm": "unsloth/qwen3.8-27b"}
    assert "reasoning_effort" not in factory.build_llm_kwargs(config)  # unset -> absent

    config["openai_reasoning_effort"] = "high"
    assert factory.build_llm_kwargs(config)["reasoning_effort"] == "high"


def test_factory_does_not_forward_reasoning_effort_to_other_providers():
    from tradingagents import default_config
    from tradingagents.llm_clients import factory

    config = {**default_config.DEFAULT_CONFIG, "llm_provider": "ollama",
              "quick_think_llm": "local-model", "openai_reasoning_effort": "high"}
    assert "reasoning_effort" not in factory.build_llm_kwargs(config)
