from __future__ import annotations

from unittest import mock

import pytest


class _Prompt:
    def __init__(self, value):
        self.value = value

    def ask(self):
        return self.value


def test_custom_provider_factory_routes_to_openai_client():
    from tradingagents.llm_clients.factory import create_llm_client
    from tradingagents.llm_clients.openai_client import OpenAIClient

    client = create_llm_client(
        provider="custom",
        model="vendor/model",
        base_url="https://llm.example.com/v1",
    )

    assert isinstance(client, OpenAIClient)
    assert client.provider == "custom"


def test_custom_provider_client_kwargs(monkeypatch):
    import tradingagents.llm_clients.openai_client as mod

    captured = {}

    class FakeChat:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("CUSTOM_PROVIDER_API_KEY", "sk-custom")
    monkeypatch.setattr(mod, "NormalizedChatOpenAI", FakeChat)

    client = mod.OpenAIClient(
        model="vendor/model",
        provider="custom",
        base_url="https://llm.example.com/v1",
    )
    assert isinstance(client.get_llm(), FakeChat)

    assert captured["model"] == "vendor/model"
    assert captured["base_url"] == "https://llm.example.com/v1"
    assert captured["api_key"] == "sk-custom"
    assert "use_responses_api" not in captured


def test_custom_provider_requires_api_key(monkeypatch):
    from tradingagents.llm_clients.openai_client import OpenAIClient

    monkeypatch.delenv("CUSTOM_PROVIDER_API_KEY", raising=False)
    client = OpenAIClient(
        model="vendor/model",
        provider="custom",
        base_url="https://llm.example.com/v1",
    )

    with pytest.raises(ValueError, match="CUSTOM_PROVIDER_API_KEY"):
        client.get_llm()


@pytest.mark.parametrize(
    "url,match",
    [
        (None, "TRADINGAGENTS_LLM_BACKEND_URL"),
        ("", "TRADINGAGENTS_LLM_BACKEND_URL"),
        ("llm.example.com/v1", "http:// or https://"),
        ("ftp://llm.example.com/v1", "http:// or https://"),
        ("https://user:secret@llm.example.com/v1", "embedded credentials"),
    ],
)
def test_custom_provider_rejects_unsafe_base_urls(url, match):
    from tradingagents.llm_clients.url_validation import validate_custom_provider_base_url

    with pytest.raises(ValueError, match=match):
        validate_custom_provider_base_url(url)


def test_custom_provider_accepts_http_and_https_base_urls():
    from tradingagents.llm_clients.url_validation import validate_custom_provider_base_url

    assert (
        validate_custom_provider_base_url(" https://llm.example.com/v1 ")
        == "https://llm.example.com/v1"
    )
    assert (
        validate_custom_provider_base_url("http://localhost:8000/v1")
        == "http://localhost:8000/v1"
    )


def test_cli_custom_provider_prompts_for_backend_url(monkeypatch):
    import cli.utils as cli_utils

    with mock.patch.object(
        cli_utils.questionary, "select", return_value=_Prompt(("custom", None))
    ), mock.patch.object(
        cli_utils.questionary,
        "text",
        return_value=_Prompt("https://llm.example.com/v1"),
    ) as text_prompt:
        provider, url = cli_utils.select_llm_provider()

    assert provider == "custom"
    assert url == "https://llm.example.com/v1"
    text_prompt.assert_called_once()


def test_cli_custom_provider_prompts_for_freeform_model_id(monkeypatch):
    import cli.utils as cli_utils

    with mock.patch.object(cli_utils, "get_model_options") as catalog, mock.patch.object(
        cli_utils.questionary,
        "text",
        return_value=_Prompt("vendor/model-fast"),
    ):
        model = cli_utils.select_shallow_thinking_agent("custom")

    assert model == "vendor/model-fast"
    catalog.assert_not_called()


def test_cli_custom_provider_model_prompt_cancel_exits(monkeypatch):
    import cli.utils as cli_utils

    with mock.patch.object(
        cli_utils.questionary,
        "text",
        return_value=_Prompt(None),
    ), mock.patch.object(cli_utils.console, "print") as print_msg:
        with pytest.raises(SystemExit):
            cli_utils.select_shallow_thinking_agent("custom")

    print_msg.assert_called_once()


def test_cli_env_custom_provider_skips_llm_prompts(monkeypatch):
    import cli.main as m

    env = {
        "TRADINGAGENTS_LLM_PROVIDER": "custom",
        "TRADINGAGENTS_DEEP_THINK_LLM": "vendor/deep",
        "TRADINGAGENTS_QUICK_THINK_LLM": "vendor/quick",
        "TRADINGAGENTS_LLM_BACKEND_URL": "https://llm.example.com/v1",
        "TRADINGAGENTS_OUTPUT_LANGUAGE": "Vietnamese",
    }
    fake_cfg = dict(m.DEFAULT_CONFIG)
    fake_cfg.update({
        "llm_provider": "custom",
        "backend_url": "https://llm.example.com/v1",
        "quick_think_llm": "vendor/quick",
        "deep_think_llm": "vendor/deep",
        "output_language": "Vietnamese",
    })

    with mock.patch.dict("os.environ", env, clear=False), \
         mock.patch.object(m, "DEFAULT_CONFIG", fake_cfg), \
         mock.patch.object(m, "fetch_announcements", return_value=None), \
         mock.patch.object(m, "display_announcements"), \
         mock.patch.object(m, "get_ticker", return_value="AAPL"), \
         mock.patch.object(m, "get_analysis_date", return_value="2026-05-29"), \
         mock.patch.object(m, "select_analysts", return_value=[]), \
         mock.patch.object(m, "select_research_depth", return_value=1), \
         mock.patch.object(m, "ensure_api_key") as ensure_key, \
         mock.patch.object(m, "select_llm_provider") as prompt_provider, \
         mock.patch.object(m, "ask_output_language") as prompt_lang, \
         mock.patch.object(m, "select_shallow_thinking_agent") as prompt_quick, \
         mock.patch.object(m, "select_deep_thinking_agent") as prompt_deep:
        sel = m.get_user_selections()

    prompt_provider.assert_not_called()
    prompt_lang.assert_not_called()
    prompt_quick.assert_not_called()
    prompt_deep.assert_not_called()
    ensure_key.assert_called_once_with("custom")
    assert sel["llm_provider"] == "custom"
    assert sel["backend_url"] == "https://llm.example.com/v1"
    assert sel["shallow_thinker"] == "vendor/quick"
    assert sel["deep_thinker"] == "vendor/deep"


def test_cli_env_custom_provider_invalid_backend_url_exits_gracefully(monkeypatch):
    import cli.main as m

    env = {
        "TRADINGAGENTS_LLM_PROVIDER": "custom",
        "TRADINGAGENTS_LLM_BACKEND_URL": "llm.example.com/v1",
        "TRADINGAGENTS_OUTPUT_LANGUAGE": "Vietnamese",
    }
    fake_cfg = dict(m.DEFAULT_CONFIG)
    fake_cfg.update({
        "llm_provider": "custom",
        "backend_url": "llm.example.com/v1",
        "output_language": "Vietnamese",
    })

    with mock.patch.dict("os.environ", env, clear=False), \
         mock.patch.object(m, "DEFAULT_CONFIG", fake_cfg), \
         mock.patch.object(m, "fetch_announcements", return_value=None), \
         mock.patch.object(m, "display_announcements"), \
         mock.patch.object(m, "get_ticker", return_value="AAPL"), \
         mock.patch.object(m, "get_analysis_date", return_value="2026-05-29"), \
         mock.patch.object(m, "select_analysts", return_value=[]), \
         mock.patch.object(m, "select_research_depth", return_value=1), \
         mock.patch.object(m, "ensure_api_key") as ensure_key, \
         mock.patch.object(m.console, "print") as print_msg:
        with pytest.raises(SystemExit):
            m.get_user_selections()

    ensure_key.assert_not_called()
    assert any("Error:" in str(call) for call in print_msg.call_args_list)
