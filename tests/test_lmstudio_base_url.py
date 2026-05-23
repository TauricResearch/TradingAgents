"""Tests for LMSTUDIO_BASE_URL env-var override across CLI and client paths."""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest


# ---- openai_client side: resolve_provider_base_url -----------------------


def _reload_client():
    import tradingagents.llm_clients.openai_client as mod
    return importlib.reload(mod)


def test_resolver_returns_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("LMSTUDIO_BASE_URL", raising=False)
    mod = _reload_client()
    assert mod.resolve_provider_base_url("lmstudio") == "http://localhost:1234/v1"


def test_resolver_returns_env_when_set(monkeypatch):
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://remote-lmstudio:1234/v1")
    mod = _reload_client()
    assert mod.resolve_provider_base_url("lmstudio") == "http://remote-lmstudio:1234/v1"


def test_resolver_evaluation_is_call_time(monkeypatch):
    """Setting the env AFTER module import must still take effect."""
    monkeypatch.delenv("LMSTUDIO_BASE_URL", raising=False)
    mod = _reload_client()
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://late-set:1234/v1")
    assert mod.resolve_provider_base_url("lmstudio") == "http://late-set:1234/v1"


def test_resolver_does_not_affect_other_providers(monkeypatch):
    """LMSTUDIO_BASE_URL should NOT leak into ollama/xai/deepseek/etc."""
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://elsewhere/v1")
    mod = _reload_client()
    assert mod.resolve_provider_base_url("ollama") == "http://localhost:11434/v1"
    assert mod.resolve_provider_base_url("xai") == "https://api.x.ai/v1"
    assert mod.resolve_provider_base_url("deepseek") == "https://api.deepseek.com"


def test_ollama_env_does_not_affect_lmstudio(monkeypatch):
    """OLLAMA_BASE_URL must not bleed into the lmstudio resolver."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama-host:11434/v1")
    monkeypatch.delenv("LMSTUDIO_BASE_URL", raising=False)
    mod = _reload_client()
    assert mod.resolve_provider_base_url("lmstudio") == "http://localhost:1234/v1"


def test_client_get_llm_picks_up_env(monkeypatch):
    """End-to-end: OpenAIClient(provider='lmstudio').get_llm() respects LMSTUDIO_BASE_URL."""
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://my-lmstudio:1234/v1")
    mod = _reload_client()
    client = mod.OpenAIClient(model="llama3.1", provider="lmstudio")
    llm = client.get_llm()
    assert "my-lmstudio" in str(llm.openai_api_base)


def test_explicit_base_url_overrides_env(monkeypatch):
    """An explicit base_url passed to the client wins over the env var."""
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://env-set:1234/v1")
    mod = _reload_client()
    client = mod.OpenAIClient(
        model="llama3.1",
        provider="lmstudio",
        base_url="http://explicit:1234/v1",
    )
    llm = client.get_llm()
    assert "explicit" in str(llm.openai_api_base)
    assert "env-set" not in str(llm.openai_api_base)


def test_lmstudio_dummy_api_key_is_provider_name(monkeypatch):
    """Local runtimes get the provider name as a dummy key, not the hardcoded 'ollama'."""
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    mod = _reload_client()
    client = mod.OpenAIClient(model="llama3.1", provider="lmstudio")
    llm = client.get_llm()
    assert llm.openai_api_key.get_secret_value() == "lmstudio"


# ---- cli.utils side: select_llm_provider dropdown -------------------------


def test_cli_dropdown_uses_env(monkeypatch, stub_questionary):
    """select_llm_provider() passes LMSTUDIO_BASE_URL to the lmstudio Choice."""
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://cli-remote:1234/v1")

    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    stub_questionary.select.return_value.ask.return_value = (
        "lmstudio", "http://cli-remote:1234/v1"
    )
    cli_utils.select_llm_provider()

    choices = stub_questionary.select.call_args[1]["choices"]
    lmstudio_url = next(
        c.value[1]
        for c in choices
        if isinstance(getattr(c, "value", None), tuple) and c.value[0] == "lmstudio"
    )
    assert lmstudio_url == "http://cli-remote:1234/v1"


def test_cli_dropdown_default_when_unset(monkeypatch, stub_questionary):
    """select_llm_provider() uses the compiled-in default when LMSTUDIO_BASE_URL is absent."""
    monkeypatch.delenv("LMSTUDIO_BASE_URL", raising=False)

    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    stub_questionary.select.return_value.ask.return_value = (
        "lmstudio", "http://localhost:1234/v1"
    )
    cli_utils.select_llm_provider()

    choices = stub_questionary.select.call_args[1]["choices"]
    lmstudio_url = next(
        c.value[1]
        for c in choices
        if isinstance(getattr(c, "value", None), tuple) and c.value[0] == "lmstudio"
    )
    assert lmstudio_url == "http://localhost:1234/v1"


# ---- confirm_lmstudio_endpoint UX -------------------------------------------


def _console_output(mock_console) -> str:
    """Flatten all console.print() calls into a single string for assertions."""
    return " ".join(
        str(call.args[0]) for call in mock_console.print.call_args_list
    )


def test_confirm_endpoint_shows_default(monkeypatch, stub_questionary):
    monkeypatch.delenv("LMSTUDIO_BASE_URL", raising=False)
    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    with patch.object(cli_utils, "console") as mock_console:
        cli_utils.confirm_lmstudio_endpoint("http://localhost:1234/v1")

    out = _console_output(mock_console)
    assert "http://localhost:1234/v1" in out
    assert "LMSTUDIO_BASE_URL" not in out  # not from env
    assert "Note" not in out               # no warnings for the canonical default


def test_confirm_endpoint_marks_env_origin(monkeypatch, stub_questionary):
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://remote-host:1234/v1")
    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    with patch.object(cli_utils, "console") as mock_console:
        cli_utils.confirm_lmstudio_endpoint("http://remote-host:1234/v1")

    out = _console_output(mock_console)
    assert "http://remote-host:1234/v1" in out
    assert "LMSTUDIO_BASE_URL" in out


def test_confirm_endpoint_warns_on_missing_scheme(monkeypatch, stub_questionary):
    """If user sets LMSTUDIO_BASE_URL=0.0.0.128, advise on the expected shape."""
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "0.0.0.128")
    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    with patch.object(cli_utils, "console") as mock_console:
        cli_utils.confirm_lmstudio_endpoint("0.0.0.128")

    out = _console_output(mock_console)
    assert "missing a scheme" in out
    assert "http://<host>:1234/v1" in out


def test_confirm_endpoint_warns_on_non_default_port_remote(monkeypatch, stub_questionary):
    """A remote host with no :1234 gets a soft hint about port mismatch."""
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://remote-host/v1")
    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    with patch.object(cli_utils, "console") as mock_console:
        cli_utils.confirm_lmstudio_endpoint("http://remote-host/v1")

    out = _console_output(mock_console)
    assert "port 1234" in out


def test_confirm_endpoint_quiet_on_local_no_port(monkeypatch, stub_questionary):
    """Local host without explicit port should not trigger the remote-port hint."""
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://localhost/v1")
    import cli.utils as cli_utils
    importlib.reload(cli_utils)

    with patch.object(cli_utils, "console") as mock_console:
        cli_utils.confirm_lmstudio_endpoint("http://localhost/v1")

    out = _console_output(mock_console)
    assert "Note" not in out


# ---- model catalog -----------------------------------------------------------


def test_lmstudio_model_labels_no_local_suffix():
    """Labels should not claim '(local)' since the endpoint is configurable."""
    from tradingagents.llm_clients.model_catalog import get_model_options
    for mode in ("quick", "deep"):
        labels = [label for label, _ in get_model_options("lmstudio", mode)]
        assert all("local" not in label for label in labels), labels


def test_lmstudio_offers_custom_model_id():
    """LM Studio users can enter any model ID loaded in their server."""
    from tradingagents.llm_clients.model_catalog import get_model_options
    for mode in ("quick", "deep"):
        entries = get_model_options("lmstudio", mode)
        values = [v for _, v in entries]
        assert "custom" in values, f"lmstudio {mode!r} missing 'custom' option: {entries}"
        assert values[-1] == "custom", f"'custom' should be last entry: {values}"


# ---- api_key_env / no auth --------------------------------------------------


def test_lmstudio_has_no_api_key_requirement():
    from tradingagents.llm_clients.api_key_env import get_api_key_env
    assert get_api_key_env("lmstudio") is None


# ---- validators: accept any model -------------------------------------------


def test_lmstudio_accepts_any_model():
    from tradingagents.llm_clients.validators import validate_model
    assert validate_model("lmstudio", "some-custom-model-from-hf") is True
    assert validate_model("lmstudio", "llama-3.3-70b-instruct") is True


# ---- factory: routes to OpenAIClient ----------------------------------------


def test_factory_creates_openai_client_for_lmstudio():
    from tradingagents.llm_clients.factory import create_llm_client
    from tradingagents.llm_clients.openai_client import OpenAIClient
    client = create_llm_client(provider="lmstudio", model="llama3.1")
    assert isinstance(client, OpenAIClient)
    assert client.provider == "lmstudio"
