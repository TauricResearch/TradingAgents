"""Tests for Tencent Cloud LKEAP Anthropic-compatible provider wiring."""

from __future__ import annotations

import pytest

from tradingagents.llm_clients.factory import (
    TENCENT_ANTHROPIC_BASE_URL,
    create_llm_client,
)


def _capture_anthropic_kwargs(monkeypatch):
    from tradingagents.llm_clients import anthropic_client as mod

    captured: dict = {}
    monkeypatch.setattr(
        mod,
        "NormalizedChatAnthropic",
        lambda **kwargs: captured.setdefault("kwargs", kwargs),
    )
    return captured


@pytest.mark.unit
def test_tencent_provider_uses_own_key_and_default_endpoint(monkeypatch):
    monkeypatch.setenv("TENCENT_API_KEY", "tc-key")
    captured = _capture_anthropic_kwargs(monkeypatch)

    client = create_llm_client(provider="tencent", model="glm-5")
    client.get_llm()

    assert captured["kwargs"]["model"] == "glm-5"
    assert captured["kwargs"]["api_key"] == "tc-key"
    assert captured["kwargs"]["base_url"] == TENCENT_ANTHROPIC_BASE_URL


@pytest.mark.unit
def test_tencent_provider_requires_key(monkeypatch):
    monkeypatch.delenv("TENCENT_API_KEY", raising=False)

    with pytest.raises(ValueError, match="TENCENT_API_KEY"):
        create_llm_client(provider="tencent", model="glm-5")


@pytest.mark.unit
def test_tencent_explicit_base_url_overrides_default(monkeypatch):
    monkeypatch.setenv("TENCENT_API_KEY", "tc-key")
    captured = _capture_anthropic_kwargs(monkeypatch)

    client = create_llm_client(
        provider="tencent",
        model="glm-5",
        base_url="https://example.test/api/anthropic",
    )
    client.get_llm()

    assert captured["kwargs"]["base_url"] == "https://example.test/api/anthropic"
