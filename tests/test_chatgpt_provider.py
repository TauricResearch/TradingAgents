"""The chatgpt provider runs on the person's ChatGPT plan.

It sends their sign-in and nothing else, only to OpenAI, in the shape plan usage
accepts (streamed, unstored, no ``system`` role); the CLI offers it under
"Subscription", checks the sign-in before a run, and lists the plan's models.
"""

import logging
from types import SimpleNamespace
from unittest import mock

import pytest
import typer
from langchain_core.messages import HumanMessage, SystemMessage

import cli.prompts as prompts
import cli.selections as selections
from tradingagents import default_config
from tradingagents.llm_clients import chatgpt_auth, factory
from tradingagents.llm_clients.openai_client import ChatGPTPlanChatOpenAI


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setattr(chatgpt_auth, "credential", lambda: (lambda: "plan-token"))
    monkeypatch.setattr(chatgpt_auth, "access_token", lambda: "plan-token")
    monkeypatch.setattr(chatgpt_auth, "signed_in_as", lambda: "a@example.com")


def _llm(**kwargs):
    config = {**default_config.DEFAULT_CONFIG, "llm_provider": "chatgpt", "openai_reasoning_effort": "high", **kwargs}
    return factory.create_llm_client("chatgpt", "gpt-5.5", **factory.build_llm_kwargs(config)).get_llm()


# --- the client ------------------------------------------------------------------

@pytest.mark.unit
def test_the_plan_is_reached_with_the_sign_in_never_an_api_key(signed_in, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-be-used")
    llm = _llm()
    assert isinstance(llm, ChatGPTPlanChatOpenAI)
    assert llm.openai_api_base == "https://api.openai.com/v1"
    assert llm.openai_api_key() == "plan-token"
    assert (llm.use_responses_api, llm.streaming, llm.store, llm.reasoning_effort) == (True, True, False, "high")


@pytest.mark.unit
def test_system_instructions_go_as_developer_and_refused_settings_are_dropped(signed_in, caplog):
    with caplog.at_level(logging.WARNING):
        llm = _llm(temperature=0.3, max_tokens=500)
    payload = llm._get_request_payload([SystemMessage("Be brief."), HumanMessage("Hi")])
    assert [item["role"] for item in payload["input"]] == ["developer", "user"]
    assert not {"temperature", "max_output_tokens"} & payload.keys()
    assert payload["stream"] is True and payload["store"] is False
    assert "does not accept temperature" in caplog.text and "does not accept max_tokens" in caplog.text


@pytest.mark.unit
def test_a_run_without_a_sign_in_stops_before_any_request(monkeypatch, tmp_path):
    monkeypatch.setattr(chatgpt_auth, "AUTH_FILE", tmp_path / "chatgpt-auth.json")
    with pytest.raises(chatgpt_auth.ChatGPTAuthError, match="tradingagents login chatgpt"):
        _llm()


@pytest.mark.unit
def test_a_chatgpt_tier_beside_an_openai_tier_keeps_each_credential(signed_in, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    config = {**default_config.DEFAULT_CONFIG, "llm_provider": "openai", "backend_url": "https://api.openai.com/v1",
              "quick_think_provider": "chatgpt", "quick_think_llm": "gpt-5.5", "deep_think_llm": "gpt-6-sol",
              "openai_reasoning_effort": "low"}
    quick = factory.create_tier_client(config, "quick").get_llm()
    deep = factory.create_tier_client(config, "deep").get_llm()
    assert isinstance(quick, ChatGPTPlanChatOpenAI) and quick.reasoning_effort == "low"
    assert quick.openai_api_key() == "plan-token"
    assert not isinstance(deep, ChatGPTPlanChatOpenAI)
    assert deep.openai_api_key.get_secret_value() == "sk-openai"


# --- the CLI ---------------------------------------------------------------------

def _menu(answers):
    """questionary.select stand-in: records each menu and answers in turn."""
    shown = []

    def select(message, choices, **kwargs):
        shown.append((message, [c.title for c in choices], kwargs.get("default")))
        return SimpleNamespace(ask=lambda: answers.pop(0)(choices))

    return shown, select


@pytest.mark.unit
def test_chatgpt_is_offered_under_subscription_after_anthropic():
    shown, select = _menu([lambda cs: next(c.value for c in cs if c.title.startswith("Subscription")),
                           lambda cs: cs[0].value])
    with mock.patch("cli.prompts.questionary.select", select):
        provider, url = prompts.select_llm_provider()
    titles = shown[0][1]
    assert titles.index("Anthropic") + 1 == titles.index(next(t for t in titles if t.startswith("Subscription")))
    assert not any(t.startswith("ChatGPT") for t in titles)
    assert shown[1][1] == ["ChatGPT (Plus or Pro plan)"]
    assert (provider, url) == ("chatgpt", "https://api.openai.com/v1")


@pytest.mark.unit
def test_a_remembered_chatgpt_choice_preselects_subscription():
    shown, select = _menu([lambda cs: ("openai", "https://api.openai.com/v1")])
    with mock.patch("cli.prompts.questionary.select", select):
        prompts.select_llm_provider(default="chatgpt")
    assert shown[0][2] == ("subscription", None)


@pytest.mark.unit
def test_a_signed_in_plan_is_named_before_the_run(signed_in, capsys):
    prompts.ensure_signed_in("chatgpt")
    assert "Using your ChatGPT plan" in capsys.readouterr().out


def _expired(monkeypatch):
    def refuse():
        raise chatgpt_auth.ChatGPTAuthError("Your ChatGPT sign-in could not be renewed (invalid_grant); "
                                            "run `tradingagents login chatgpt` again.")
    monkeypatch.setattr(chatgpt_auth, "access_token", refuse)


@pytest.mark.unit
def test_an_unattended_run_with_a_dead_sign_in_says_how_to_sign_in(monkeypatch, capsys):
    _expired(monkeypatch)
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: False))
    with pytest.raises(typer.Exit):
        prompts.ensure_signed_in("chatgpt")
    assert "tradingagents login chatgpt" in " ".join(capsys.readouterr().out.split())


@pytest.mark.unit
def test_an_interactive_run_signs_in_again_through_the_login_command(monkeypatch, capsys):
    _expired(monkeypatch)
    monkeypatch.setattr(chatgpt_auth, "signed_in_as", lambda: "a@example.com")
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    ran = []
    monkeypatch.setattr(prompts.subprocess, "run", lambda argv: ran.append(argv) or SimpleNamespace(returncode=0))
    prompts.ensure_signed_in("chatgpt")
    assert ran[0][1:] == ["-P", "-m", "cli.main", "login", "chatgpt"]
    assert "Using your ChatGPT plan" in capsys.readouterr().out


@pytest.mark.unit
def test_each_tier_s_provider_is_signed_in_or_keyed(monkeypatch):
    monkeypatch.setitem(selections.DEFAULT_CONFIG, "quick_think_provider", "chatgpt")
    monkeypatch.setitem(selections.DEFAULT_CONFIG, "deep_think_provider", None)
    monkeypatch.setenv("TRADINGAGENTS_QUICK_THINK_LLM", "gpt-5.5")
    signed, keyed = [], []
    monkeypatch.setattr(selections, "ensure_signed_in", signed.append)
    monkeypatch.setattr(selections, "ensure_api_key", keyed.append)
    selections._check_tier_providers("openai")
    assert signed == ["chatgpt", "openai"] and keyed == ["chatgpt", "openai"]


@pytest.mark.unit
def test_the_plan_s_listed_models_are_offered_in_openai_s_order(signed_in, monkeypatch):
    monkeypatch.setattr(chatgpt_auth, "access_token", lambda: "plan-token")
    body = {"models": [
        {"slug": "gpt-5.5", "display_name": "GPT-5.5", "visibility": "list", "priority": 9},
        {"slug": "internal", "display_name": "Internal", "visibility": "hide", "priority": 0},
        {"slug": "gpt-6-astra", "display_name": "GPT-6-Astra", "visibility": "list", "priority": 2},
    ]}
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)
    with mock.patch("requests.get", return_value=response) as get:
        assert chatgpt_auth.list_models() == [("GPT-6-Astra", "gpt-6-astra"), ("GPT-5.5", "gpt-5.5")]
    assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer plan-token"}


@pytest.mark.unit
def test_api_organization_and_project_do_not_travel_with_the_sign_in(signed_in, monkeypatch):
    monkeypatch.setenv("OPENAI_ORG_ID", "org-for-api-keys")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "proj-for-api-keys")
    llm = _llm()
    for client in (llm.root_client, llm.root_async_client):
        sent = {k: v for k, v in client.default_headers.items() if isinstance(v, str)}
        assert "OpenAI-Organization" not in sent and "OpenAI-Project" not in sent


@pytest.mark.unit
def test_a_remembered_plan_model_is_offered_again():
    from cli.prefs import sanitize

    kept = sanitize({"llm_provider": "chatgpt", "quick_think_llm": "gpt-5.5", "deep_think_llm": "gpt-6-astra"}, "stock")
    assert (kept["quick_think_llm"], kept["deep_think_llm"]) == ("gpt-5.5", "gpt-6-astra")


@pytest.mark.unit
def test_a_malformed_model_entry_does_not_hide_the_others(signed_in):
    body = {"models": [{"display_name": "No slug", "visibility": "list"},
                       {"slug": "gpt-5.5", "display_name": "GPT-5.5", "visibility": "list"}]}
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)
    with mock.patch("requests.get", return_value=response):
        assert chatgpt_auth.list_models() == [("GPT-5.5", "gpt-5.5")]


@pytest.mark.unit
def test_an_unreachable_openai_stops_the_run_without_a_new_sign_in(monkeypatch, capsys):
    def unreachable():
        raise chatgpt_auth.ChatGPTUnreachable("Could not reach OpenAI to renew your ChatGPT sign-in; try again.")

    monkeypatch.setattr(chatgpt_auth, "access_token", unreachable)
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(prompts.subprocess, "run", lambda argv: pytest.fail("offered a new sign-in"))
    with pytest.raises(typer.Exit):
        prompts.ensure_signed_in("chatgpt")
    assert "try again" in capsys.readouterr().out


@pytest.mark.unit
@pytest.mark.parametrize("main, tier_provider, tier_url, backend_url", [
    ("chatgpt", None, None, "http://localhost:8000/v1"),          # the run's own endpoint
    ("openai", "chatgpt", "http://relay.example/v1", None),        # a chatgpt tier's endpoint
])
def test_a_plan_pointed_at_another_endpoint_stops_before_the_run(monkeypatch, capsys, main, tier_provider,
                                                                  tier_url, backend_url):
    monkeypatch.setitem(selections.DEFAULT_CONFIG, "quick_think_provider", tier_provider)
    monkeypatch.setitem(selections.DEFAULT_CONFIG, "quick_think_backend_url", tier_url)
    monkeypatch.setitem(selections.DEFAULT_CONFIG, "deep_think_provider", None)
    monkeypatch.setenv("TRADINGAGENTS_QUICK_THINK_LLM", "gpt-6-luna")
    monkeypatch.setattr(selections, "ensure_signed_in", lambda p: pytest.fail("checked the sign-in first"))
    with pytest.raises(typer.Exit):
        selections._check_tier_providers(main, backend_url)
    assert "only connects to https://api.openai.com/v1" in " ".join(capsys.readouterr().out.split())


@pytest.mark.unit
def test_a_remembered_openrouter_model_is_preselected(monkeypatch):
    monkeypatch.setattr(prompts, "_fetch_openrouter_models",
                        lambda: [("A", "openai/a"), ("B", "anthropic/b")])
    shown, select = _menu([lambda cs: cs[1].value])
    with mock.patch("cli.prompts.questionary.select", select):
        assert prompts.select_openrouter_model("deep", default="anthropic/b") == "anthropic/b"
    assert shown[0][2] == "anthropic/b"


@pytest.mark.unit
def test_the_chatgpt_plan_is_the_only_provider_signed_in_to():
    # `login`, `logout` and the pre-run check are wired to the ChatGPT sign-in; a
    # second signed-in provider needs its own sign-in wired into them first.
    from tradingagents.llm_clients.openai_client import SIGNED_IN_PROVIDERS
    assert SIGNED_IN_PROVIDERS == ("chatgpt",)
