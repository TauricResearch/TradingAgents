from __future__ import annotations

import cli.utils as cli_utils


def _fail_if_prompted(*args, **kwargs):
    raise AssertionError("CLI prompt should not be called when env vars are configured")


def test_select_llm_provider_uses_tradingagents_env(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    monkeypatch.setenv(
        "TRADINGAGENTS_LLM_BACKEND_URL",
        "https://opencode.ai/zen/go/v1",
    )

    monkeypatch.setattr(cli_utils.questionary, "select", _fail_if_prompted)

    provider, backend_url = cli_utils.select_llm_provider()

    assert provider == "openai"
    assert backend_url == "https://opencode.ai/zen/go/v1"


def test_select_quick_model_uses_tradingagents_env(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_QUICK_THINK_LLM", "deepseek-v4-pro")

    monkeypatch.setattr(cli_utils.questionary, "select", _fail_if_prompted)

    model = cli_utils._select_model("openai", "quick")

    assert model == "deepseek-v4-pro"


def test_select_deep_model_uses_tradingagents_env(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_DEEP_THINK_LLM", "kimi-k2.5")

    monkeypatch.setattr(cli_utils.questionary, "select", _fail_if_prompted)

    model = cli_utils._select_model("openai", "deep")

    assert model == "kimi-k2.5"