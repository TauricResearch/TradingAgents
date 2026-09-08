"""CLI surface for the openai_codex provider.

Codex has no API-key env var, so the usual ensure_api_key prompt is a no-op for
it. Without a preflight the run would look configured and then fail on the first
LLM call, so ensure_api_key validates the Codex auth file instead.
"""
from __future__ import annotations

import pytest

from cli.utils import _llm_provider_table, ensure_api_key
from tradingagents.llm_clients import codex_auth
from tradingagents.llm_clients.model_catalog import get_model_options


@pytest.mark.unit
def test_dropdown_offers_codex():
    rows = {key: (label, url) for label, key, url in _llm_provider_table()}
    label, url = rows["openai_codex"]
    assert url == "https://chatgpt.com/backend-api/codex"
    assert "subscription" in label.lower()


@pytest.mark.unit
@pytest.mark.parametrize("mode,expected_first", [("quick", "gpt-5.4-mini"), ("deep", "gpt-5.6-sol")])
def test_catalog_defaults(mode, expected_first):
    options = get_model_options("openai_codex", mode)
    assert options[0][1] == expected_first
    assert options[-1][1] == "custom"


@pytest.mark.unit
def test_preflight_passes_when_credentials_resolve(monkeypatch):
    monkeypatch.setattr(
        codex_auth, "resolve",
        lambda *a, **k: codex_auth.CodexCredentials(token="t", account_id="a"),
    )
    assert ensure_api_key("openai_codex") is None


@pytest.mark.unit
def test_preflight_exits_when_credentials_are_missing(monkeypatch):
    def _fail(*args, **kwargs):
        raise codex_auth.CodexAuthError("no credentials at ~/.codex/auth.json")

    monkeypatch.setattr(codex_auth, "resolve", _fail)
    with pytest.raises(SystemExit):
        ensure_api_key("openai_codex")


@pytest.mark.unit
def test_other_keyless_providers_are_unaffected(monkeypatch):
    def _explode(*args, **kwargs):
        raise AssertionError("ollama must not touch Codex auth")

    monkeypatch.setattr(codex_auth, "resolve", _explode)
    assert ensure_api_key("ollama") is None
