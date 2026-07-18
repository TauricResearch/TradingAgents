"""ChatGPT OAuth-backed OpenAI Codex provider wiring."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.validators import validate_model


@pytest.mark.unit
def test_factory_routes_to_codex_client():
    client = create_llm_client(provider="openai_codex", model="gpt-5.3-codex")
    assert type(client).__name__ == "OpenAICodexClient"


@pytest.mark.unit
def test_no_api_key_required_and_any_model_accepted():
    assert get_api_key_env("openai_codex") is None
    assert validate_model("openai_codex", "account-specific-model") is True


@pytest.mark.unit
def test_get_llm_uses_langchain_codex_client(monkeypatch):
    captured = {}

    class FakeCodex:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def invoke(self, input, config=None, **kwargs):
            return SimpleNamespace(
                content=[
                    {"type": "reasoning", "summary": []},
                    {"type": "text", "text": "normalized"},
                ]
            )

    module = types.ModuleType("langchain_openai.chat_models.codex")
    module._ChatOpenAICodex = FakeCodex
    package = types.ModuleType("langchain_openai")
    package.__path__ = []
    chat_models_package = types.ModuleType("langchain_openai.chat_models")
    chat_models_package.__path__ = []
    monkeypatch.setitem(sys.modules, "langchain_openai", package)
    monkeypatch.setitem(
        sys.modules,
        "langchain_openai.chat_models",
        chat_models_package,
    )
    monkeypatch.setitem(sys.modules, "langchain_openai.chat_models.codex", module)
    monkeypatch.setenv("TRADINGAGENTS_CODEX_ORIGINATOR", "tests")

    llm = create_llm_client("openai_codex", "gpt-5.3-codex", max_retries=3).get_llm()

    assert captured["model"] == "gpt-5.3-codex"
    assert captured["originator"] == "tests"
    assert captured["max_retries"] == 3
    assert llm.invoke("hi").content == "normalized"


@pytest.mark.unit
def test_base_url_is_rejected():
    with pytest.raises(ValueError, match="does not accept backend_url"):
        create_llm_client(
            "openai_codex", "gpt-5.3-codex", base_url="http://proxy/v1"
        ).get_llm()


@pytest.mark.unit
def test_helpful_error_when_langchain_codex_client_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "langchain_openai.chat_models.codex", None)
    with pytest.raises(ImportError, match="langchain-openai>=1.3.3"):
        create_llm_client("openai_codex", "gpt-5.3-codex").get_llm()


@pytest.mark.unit
def test_cli_model_options_include_codex_provider():
    from tradingagents.llm_clients.model_catalog import get_model_options

    quick_values = {value for _, value in get_model_options("openai_codex", "quick")}
    deep_values = {value for _, value in get_model_options("openai_codex", "deep")}
    assert "gpt-5.3-codex-spark" in quick_values
    assert "gpt-5.3-codex" in deep_values
    assert "custom" in quick_values


@pytest.mark.unit
def test_app_server_model_response_is_normalized(monkeypatch):
    from tradingagents.llm_clients.codex_app_server import CodexAppServerClient

    responses = [
        {
            "data": [
                {
                    "id": "gpt-5.3-codex",
                    "model": "gpt-5.3-codex",
                    "displayName": "GPT-5.3 Codex",
                    "description": "Strong coding model",
                    "isDefault": True,
                    "hidden": False,
                    "defaultReasoningEffort": "high",
                }
            ],
            "nextCursor": "page-2",
        },
        {
            "data": [
                {
                    "id": "gpt-5.3-codex-spark",
                    "model": "gpt-5.3-codex-spark",
                    "displayName": "GPT-5.3 Codex Spark",
                    "description": "Fast coding model",
                    "hidden": False,
                    "defaultReasoningEffort": "medium",
                }
            ],
            "nextCursor": None,
        },
    ]

    client = CodexAppServerClient()
    monkeypatch.setattr(client, "_request", lambda *_args, **_kwargs: responses.pop(0))

    models = client.list_models()

    assert [model.model for model in models] == [
        "gpt-5.3-codex",
        "gpt-5.3-codex-spark",
    ]
    assert models[0].display_name == "GPT-5.3 Codex"
    assert models[0].is_default is True


@pytest.mark.unit
def test_app_server_stderr_buffer_is_bounded():
    from tradingagents.llm_clients.codex_app_server import CodexAppServerClient

    client = CodexAppServerClient()
    for index in range(25):
        client._stderr_lines.append(f"line-{index}")

    assert len(client._stderr_lines) == 20
    assert client._stderr_summary() == "line-22 line-23 line-24"


@pytest.mark.unit
def test_app_server_enter_closes_when_initialize_fails(monkeypatch):
    from tradingagents.llm_clients.codex_app_server import CodexAppServerClient

    client = CodexAppServerClient()
    calls = []

    def fail_initialize():
        raise RuntimeError("init failed")

    monkeypatch.setattr(client, "_start", lambda: calls.append("start"))
    monkeypatch.setattr(client, "_initialize", fail_initialize)
    monkeypatch.setattr(client, "close", lambda: calls.append("close"))

    with pytest.raises(RuntimeError, match="init failed"):
        client.__enter__()

    assert calls == ["start", "close"]


@pytest.mark.unit
def test_app_server_send_wraps_closed_stdin():
    from tradingagents.llm_clients.codex_app_server import (
        CodexAppServerClient,
        CodexAppServerError,
    )

    class ClosedStdin:
        @staticmethod
        def write(_value):
            raise ValueError("I/O operation on closed file")

        @staticmethod
        def flush():
            raise AssertionError("flush should not be called after write failure")

    client = CodexAppServerClient()
    client._proc = SimpleNamespace(stdin=ClosedStdin())
    client._stderr_lines.append("app-server exited")

    with pytest.raises(CodexAppServerError, match="Failed to write to Codex app-server"):
        client._send({"method": "model/list"})


@pytest.mark.unit
def test_app_server_close_closes_stdio_streams():
    from tradingagents.llm_clients.codex_app_server import CodexAppServerClient

    class Pipe:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class Process:
        def __init__(self):
            self.stdin = Pipe()
            self.stdout = Pipe()
            self.stderr = Pipe()

        @staticmethod
        def poll():
            return 0

    process = Process()
    client = CodexAppServerClient()
    client._proc = process

    client.close()

    assert process.stdin.closed is True
    assert process.stdout.closed is True
    assert process.stderr.closed is True
    assert client._proc is None


@pytest.mark.unit
def test_cli_fetches_codex_models_from_app_server(monkeypatch):
    import cli.utils as cli_utils
    from tradingagents.llm_clients.codex_app_server import CodexModelInfo

    monkeypatch.setattr(cli_utils, "_CODEX_MODEL_OPTIONS_CACHE", None)
    monkeypatch.setattr(
        "tradingagents.llm_clients.codex_app_server.list_codex_app_server_models",
        lambda **_kwargs: [
            CodexModelInfo(
                id="gpt-5.3-codex",
                model="gpt-5.3-codex",
                display_name="GPT-5.3 Codex",
                description="Strong coding model",
                is_default=True,
                default_reasoning_effort="high",
            ),
            CodexModelInfo(
                id="hidden-model",
                model="hidden-model",
                display_name="Hidden",
                description="Hidden model",
                hidden=True,
            ),
        ],
    )

    options = cli_utils._fetch_codex_model_options()

    assert options == [
        ("GPT-5.3 Codex [gpt-5.3-codex] (default, effort: high)", "gpt-5.3-codex")
    ]


@pytest.mark.unit
def test_ensure_openai_codex_auth_uses_existing_token(monkeypatch):
    import cli.utils as cli_utils
    from tradingagents.llm_clients.codex_oauth import ChatGPTOAuthStatus

    monkeypatch.setattr(
        "tradingagents.llm_clients.codex_oauth.get_chatgpt_oauth_status",
        lambda: ChatGPTOAuthStatus(account_id="acct", plan_type="plus", user_id="user"),
    )
    monkeypatch.setattr(cli_utils.questionary, "select", pytest.fail)

    cli_utils.ensure_openai_codex_auth("openai_codex")


@pytest.mark.unit
def test_ensure_openai_codex_auth_runs_login_when_missing(monkeypatch):
    import cli.utils as cli_utils
    import tradingagents.llm_clients.codex_oauth as oauth
    from tradingagents.llm_clients.codex_oauth import ChatGPTOAuthStatus

    calls = {"login": None}

    def missing_status():
        raise oauth.CodexOAuthMissingTokenError("missing")

    def login(*, device_code):
        calls["login"] = device_code
        return ChatGPTOAuthStatus(account_id="acct", plan_type="pro", user_id="user")

    class Prompt:
        @staticmethod
        def ask():
            return "device"

    monkeypatch.setattr(oauth, "get_chatgpt_oauth_status", missing_status)
    monkeypatch.setattr(oauth, "login_chatgpt_oauth", login)
    monkeypatch.setattr(cli_utils.questionary, "select", lambda *_, **__: Prompt())

    cli_utils.ensure_openai_codex_auth("openai_codex")

    assert calls["login"] is True


@pytest.mark.unit
def test_openai_reasoning_effort_menu_includes_xhigh(monkeypatch):
    import cli.utils as cli_utils

    captured = {}

    class Prompt:
        @staticmethod
        def ask():
            return "xhigh"

    def fake_select(_message, *, choices, **_kwargs):
        captured["values"] = [choice.value for choice in choices]
        return Prompt()

    monkeypatch.setattr(cli_utils.questionary, "select", fake_select)

    assert cli_utils.ask_openai_reasoning_effort() == "xhigh"
    assert captured["values"] == ["medium", "high", "xhigh", "low"]
