import pytest

from tradingagents.llm_clients import anthropic_client as mod


@pytest.mark.unit
def test_haiku_does_not_receive_effort(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        mod,
        "NormalizedChatAnthropic",
        lambda **kwargs: captured.setdefault("kwargs", kwargs),
    )

    client = mod.AnthropicClient(
        model="claude-haiku-4-5", effort="medium", api_key="placeholder"
    )
    client.get_llm()

    assert "effort" not in captured["kwargs"]
    assert captured["kwargs"]["api_key"] == "placeholder"


@pytest.mark.unit
@pytest.mark.parametrize(
    "model",
    [
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-opus-4-5",
        "claude-sonnet-4-6",
    ],
)
def test_effort_capable_models_receive_effort(monkeypatch, model):
    captured = {}
    monkeypatch.setattr(
        mod,
        "NormalizedChatAnthropic",
        lambda **kwargs: captured.setdefault("kwargs", kwargs),
    )

    client = mod.AnthropicClient(
        model=model, effort="medium", api_key="placeholder"
    )
    client.get_llm()

    assert captured["kwargs"]["effort"] == "medium"

