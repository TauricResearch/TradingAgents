"""Tests for OLLAMA_BASE_URL env-var override across CLI and client paths."""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest


# ---- openai_client side: resolve_provider_base_url -----------------------


def _reload_client():
    import tradingagents.llm_clients.openai_client as mod
    return importlib.reload(mod)


def test_resolver_returns_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    mod = _reload_client()
    assert mod.resolve_provider_base_url("ollama") == "http://localhost:11434/v1"


def test_resolver_returns_env_when_set(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote-ollama:11434/v1")
    mod = _reload_client()
    assert mod.resolve_provider_base_url("ollama") == "http://remote-ollama:11434/v1"


def test_resolver_evaluation_is_call_time(monkeypatch):
    """Setting the env AFTER module import must still take effect."""
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    mod = _reload_client()
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://late-set:11434/v1")
    assert mod.resolve_provider_base_url("ollama") == "http://late-set:11434/v1"


def test_resolver_does_not_affect_other_providers(monkeypatch):
    """OLLAMA_BASE_URL should NOT leak into xai/deepseek/etc."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://elsewhere/v1")
    mod = _reload_client()
    assert mod.resolve_provider_base_url("xai") == "https://api.x.ai/v1"
    assert mod.resolve_provider_base_url("deepseek") == "https://api.deepseek.com"


def test_client_get_llm_picks_up_env(monkeypatch):
    """End-to-end: OpenAIClient(provider='ollama').get_llm() respects OLLAMA_BASE_URL."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://my-ollama:11434/v1")
    mod = _reload_client()
    client = mod.OpenAIClient(model="llama3.1", provider="ollama")
    llm = client.get_llm()
    assert "my-ollama" in str(llm.openai_api_base)


def test_explicit_base_url_overrides_env(monkeypatch):
    """An explicit base_url passed to the client wins over the env var."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://env-set:11434/v1")
    mod = _reload_client()
    client = mod.OpenAIClient(
        model="llama3.1",
        provider="ollama",
        base_url="http://explicit:11434/v1",
    )
    llm = client.get_llm()
    assert "explicit" in str(llm.openai_api_base)
    assert "env-set" not in str(llm.openai_api_base)


# ---- cli.utils side: select_llm_provider dropdown -------------------------


def test_cli_dropdown_uses_env(monkeypatch, stub_questionary):
    """select_llm_provider() passes OLLAMA_BASE_URL to the ollama Choice."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://cli-remote:11434/v1")

    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    stub_questionary.select.return_value.ask.return_value = (
        "ollama", "http://cli-remote:11434/v1"
    )
    cli_utils.select_llm_provider()

    choices = stub_questionary.select.call_args[1]["choices"]
    ollama_url = next(
        c.value[1]
        for c in choices
        if isinstance(getattr(c, "value", None), tuple) and c.value[0] == "ollama"
    )
    assert ollama_url == "http://cli-remote:11434/v1"


def test_cli_dropdown_default_when_unset(monkeypatch, stub_questionary):
    """select_llm_provider() uses the compiled-in default when OLLAMA_BASE_URL is absent."""
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    stub_questionary.select.return_value.ask.return_value = (
        "ollama", "http://localhost:11434/v1"
    )
    cli_utils.select_llm_provider()

    choices = stub_questionary.select.call_args[1]["choices"]
    ollama_url = next(
        c.value[1]
        for c in choices
        if isinstance(getattr(c, "value", None), tuple) and c.value[0] == "ollama"
    )
    assert ollama_url == "http://localhost:11434/v1"


# ---- confirm_ollama_endpoint UX -------------------------------------------


def _console_output(mock_console) -> str:
    """Flatten all console.print() calls into a single string for assertions."""
    return " ".join(
        str(call.args[0]) for call in mock_console.print.call_args_list
    )


def test_confirm_endpoint_shows_default(monkeypatch, stub_questionary):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    with patch.object(cli_utils, "console") as mock_console:
        cli_utils.confirm_ollama_endpoint("http://localhost:11434/v1")

    out = _console_output(mock_console)
    assert "http://localhost:11434/v1" in out
    assert "OLLAMA_BASE_URL" not in out  # not from env
    assert "Note" not in out             # no warnings for the canonical default


def test_confirm_endpoint_marks_env_origin(monkeypatch, stub_questionary):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote-host:11434/v1")
    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    with patch.object(cli_utils, "console") as mock_console:
        cli_utils.confirm_ollama_endpoint("http://remote-host:11434/v1")

    out = _console_output(mock_console)
    assert "http://remote-host:11434/v1" in out
    assert "OLLAMA_BASE_URL" in out


def test_confirm_endpoint_warns_on_missing_scheme(monkeypatch, stub_questionary):
    """If user sets OLLAMA_BASE_URL=0.0.0.128, advise on the expected shape."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "0.0.0.128")
    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    with patch.object(cli_utils, "console") as mock_console:
        cli_utils.confirm_ollama_endpoint("0.0.0.128")

    out = _console_output(mock_console)
    assert "missing a scheme" in out
    assert "http://<host>:11434/v1" in out


def test_confirm_endpoint_warns_on_non_default_port_remote(monkeypatch, stub_questionary):
    """A remote host with no :11434 gets a soft hint about port mismatch."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote-host/v1")
    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    with patch.object(cli_utils, "console") as mock_console:
        cli_utils.confirm_ollama_endpoint("http://remote-host/v1")

    out = _console_output(mock_console)
    assert "port 11434" in out


def test_confirm_endpoint_quiet_on_local_no_port(monkeypatch, stub_questionary):
    """Local host without port shouldn't trigger the remote-port hint."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost/v1")
    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    with patch.object(cli_utils, "console") as mock_console:
        cli_utils.confirm_ollama_endpoint("http://localhost/v1")

    out = _console_output(mock_console)
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
