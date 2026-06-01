"""Tests for Anthropic temperature-parameter gating.

Extended-thinking / reasoning models (the Opus/Sonnet line that accept
``effort``) deprecate ``temperature`` and 400 with
``"`temperature` is deprecated for this model."``. Non-reasoning models
(e.g. Haiku) still honor it. The gate reuses the same forward-compat
effort pattern so future ``claude-{opus,sonnet}-X-Y`` releases inherit
the behavior automatically.
"""

import pytest

from tradingagents.llm_clients import anthropic_client as mod


def _capture_kwargs(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        mod, "NormalizedChatAnthropic",
        lambda **kwargs: captured.setdefault("kwargs", kwargs),
    )
    return captured


@pytest.mark.unit
class TestTemperatureGate:
    @pytest.mark.parametrize(
        "model",
        ["claude-haiku-4-5", "claude-haiku-5-0", "claude-3-5-haiku"],
    )
    def test_haiku_receives_temperature(self, monkeypatch, model):
        captured = _capture_kwargs(monkeypatch)
        mod.AnthropicClient(model=model, temperature=0.7, api_key="x").get_llm()
        assert captured["kwargs"]["temperature"] == 0.7

    @pytest.mark.parametrize(
        "model",
        [
            "claude-opus-4-5", "claude-opus-4-6", "claude-opus-4-8",
            "claude-sonnet-4-5", "claude-sonnet-4-6", "claude-opus-5-0",
        ],
    )
    def test_reasoning_models_do_not_receive_temperature(self, monkeypatch, model):
        captured = _capture_kwargs(monkeypatch)
        mod.AnthropicClient(model=model, temperature=0.7, api_key="x").get_llm()
        assert "temperature" not in captured["kwargs"]

    def test_unknown_model_receives_temperature(self, monkeypatch):
        """Unknown (non-reasoning) models keep temperature — they're not effort-capable."""
        captured = _capture_kwargs(monkeypatch)
        mod.AnthropicClient(
            model="claude-experimental-x", temperature=0.3, api_key="x"
        ).get_llm()
        assert captured["kwargs"]["temperature"] == 0.3

    def test_other_kwargs_still_forwarded_when_temperature_skipped(self, monkeypatch):
        """Skipping temperature must not break other passthrough kwargs."""
        captured = _capture_kwargs(monkeypatch)
        mod.AnthropicClient(
            model="claude-opus-4-8",
            temperature=0.7,
            effort="high",
            api_key="placeholder",
            max_tokens=2048,
        ).get_llm()
        assert captured["kwargs"]["api_key"] == "placeholder"
        assert captured["kwargs"]["max_tokens"] == 2048
        assert captured["kwargs"]["effort"] == "high"
        assert "temperature" not in captured["kwargs"]
