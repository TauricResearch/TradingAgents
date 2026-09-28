"""Tests for OLLAMA_BASE_URL env-var override across CLI and client paths."""

from __future__ import annotations

import re

import pytest

# Rich colorizes console output and highlights numbers and URLs, which splits
# asserted substrings with escape codes ("port \x1b[1;33m11434"). Whether it
# does so depends on the ambient terminal, so strip the codes to keep these
# assertions independent of where the suite runs.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _console_out(capsys) -> str:
    return _ANSI.sub("", capsys.readouterr().out)


# ---- openai_client side: registry-driven base_url resolution --------------


def _client_module():
    import tradingagents.llm_clients.openai_client as mod
    return mod


def _base_url(mod, provider, **kwargs):
    return str(mod.OpenAIClient(model="m", provider=provider, **kwargs).get_llm().openai_api_base)


def test_resolver_returns_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    mod = _client_module()
    assert _base_url(mod, "ollama") == "http://localhost:11434/v1"


def test_resolver_returns_env_when_set(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote-ollama:11434/v1")
    mod = _client_module()
    assert _base_url(mod, "ollama") == "http://remote-ollama:11434/v1"


def test_resolver_evaluation_is_call_time(monkeypatch):
    """Setting the env AFTER module import must still take effect."""
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    mod = _client_module()
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://late-set:11434/v1")
    assert _base_url(mod, "ollama") == "http://late-set:11434/v1"


def test_resolver_does_not_affect_other_providers(monkeypatch):
    """OLLAMA_BASE_URL should NOT leak into xai/deepseek/etc."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://elsewhere/v1")
    mod = _client_module()
    assert _base_url(mod, "xai") == "https://api.x.ai/v1"
    assert _base_url(mod, "deepseek") == "https://api.deepseek.com"


def test_client_get_llm_picks_up_env(monkeypatch):
    """End-to-end: OllamaClient.get_llm() respects OLLAMA_BASE_URL."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://my-ollama:11434/v1")
    mod = _client_module()
    client = mod.OpenAIClient(model="llama3.1", provider="ollama")
    llm = client.get_llm()
    assert "my-ollama" in str(llm.openai_api_base)


def test_explicit_base_url_overrides_env(monkeypatch):
    """An explicit base_url passed to the client wins over the env var."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://env-set:11434/v1")
    mod = _client_module()
    client = mod.OpenAIClient(
        model="llama3.1",
        provider="ollama",
        base_url="http://explicit:11434/v1",
    )
    llm = client.get_llm()
    assert "explicit" in str(llm.openai_api_base)
    assert "env-set" not in str(llm.openai_api_base)


# ---- confirm_ollama_endpoint UX -------------------------------------------


def test_confirm_endpoint_shows_default(monkeypatch, capsys):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    from cli import prompts
    prompts.confirm_ollama_endpoint("http://localhost:11434/v1")
    out = _console_out(capsys)
    assert "http://localhost:11434/v1" in out
    assert "OLLAMA_BASE_URL" not in out  # not from env
    assert "Note" not in out  # no warnings for the canonical default


def test_confirm_endpoint_marks_env_origin(monkeypatch, capsys):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote-host:11434/v1")
    from cli import prompts
    prompts.confirm_ollama_endpoint("http://remote-host:11434/v1")
    out = _console_out(capsys)
    assert "http://remote-host:11434/v1" in out
    assert "OLLAMA_BASE_URL" in out


def test_confirm_endpoint_warns_on_missing_scheme(monkeypatch, capsys):
    """If user sets OLLAMA_BASE_URL=0.0.0.128, advise on the expected shape."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "0.0.0.128")
    from cli import prompts
    prompts.confirm_ollama_endpoint("0.0.0.128")
    out = _console_out(capsys)
    assert "missing a scheme" in out
    assert "http://<host>:11434/v1" in out


def test_confirm_endpoint_warns_on_non_default_port_remote(monkeypatch, capsys):
    """A remote host with no :11434 gets a soft hint about port mismatch."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote-host/v1")
    from cli import prompts
    prompts.confirm_ollama_endpoint("http://remote-host/v1")
    out = _console_out(capsys)
    assert "port 11434" in out


def test_confirm_endpoint_quiet_on_local_no_port(monkeypatch, capsys):
    """Local host without port shouldn't trigger the remote-port hint."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost/v1")
    from cli import prompts
    prompts.confirm_ollama_endpoint("http://localhost/v1")
    out = _console_out(capsys)
    assert "Note" not in out  # localhost is fine without explicit port


def test_ollama_model_labels_no_local_suffix():
    """Labels should no longer claim '(local)' since the endpoint is dynamic."""
    from tradingagents.llm_clients.model_catalog import get_model_options
    for mode in ("quick", "deep"):
        labels = [label for label, _ in get_model_options("ollama", mode)]
        assert all("local" not in label for label in labels), labels


def test_ollama_offers_custom_model_id():
    """Ollama users with custom-pulled models can pick 'Custom model ID'."""
    from tradingagents.llm_clients.model_catalog import get_model_options
    for mode in ("quick", "deep"):
        entries = get_model_options("ollama", mode)
        values = [v for _, v in entries]
        assert "custom" in values, f"Ollama {mode!r} missing 'custom' option: {entries}"
        # Custom option is last so it doesn't push the curated defaults off-screen
        assert values[-1] == "custom", f"'custom' should be last entry: {values}"


def _capture_structured_output(monkeypatch, provider, model, base_url=None):
    """Bind a schema and capture the kwargs the client hands to langchain's
    ``with_structured_output`` (the base class is monkeypatched, so only what
    the client explicitly sets lands in the captured dict)."""
    from langchain_openai import ChatOpenAI
    from pydantic import BaseModel

    from tradingagents.llm_clients import create_llm_client

    class Schema(BaseModel):
        x: int

    captured = {}
    monkeypatch.setattr(
        ChatOpenAI,
        "with_structured_output",
        lambda self, schema, method=None, **kw: captured.update({"method": method, **kw}) or "BOUND",
    )

    client = create_llm_client(provider=provider, model=model, base_url=base_url)
    client.get_llm().with_structured_output(Schema)
    return captured


@pytest.mark.unit
def test_ollama_lets_tool_choice_through(monkeypatch):
    """Ollama accepts the object-form ``tool_choice`` langchain sends for
    function-calling structured output, so the client must NOT pin it to None.
    Letting it through forces the model to call the schema tool instead of
    answering in free text — which thinking models (e.g. Qwen3) otherwise do on
    long prompts, returning no parsed result and tripping the free-text fallback.
    (Generic local servers still suppress it; see the companion test.)"""
    captured = _capture_structured_output(monkeypatch, "ollama", "qwen3:30b")

    # The client must not suppress tool_choice; langchain sends the object-form
    # tool_choice, which Ollama accepts.
    assert "tool_choice" not in captured
    assert captured["method"] == "function_calling"


@pytest.mark.unit
def test_generic_local_server_suppresses_tool_choice(monkeypatch):
    """Generic local servers (LM Studio, vLLM, llama.cpp via the
    ``openai_compatible`` provider) reject the object-form ``tool_choice``, so
    the client pins it to None while still binding the schema as a tool (#1057)."""
    captured = _capture_structured_output(
        monkeypatch, "openai_compatible", "local-model", base_url="http://localhost:8000/v1"
    )

    assert captured["tool_choice"] is None
    assert captured["method"] == "function_calling"
