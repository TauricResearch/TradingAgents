"""CLI coverage for explicit ChatGPT subscription authentication."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from cli import auth, main, prompts, selections
from cli.run import _build_run_config
from tradingagents.llm_clients import chatgpt_auth

runner = CliRunner()


@pytest.mark.unit
def test_auth_login_parses_provider_and_add_account(monkeypatch):
    calls = []
    monkeypatch.setattr(
        auth.chatgpt_auth,
        "sign_in",
        lambda **kwargs: calls.append(kwargs)
        or SimpleNamespace(inference_enabled=True),
    )

    result = runner.invoke(main.app, ["auth", "login", "--provider", "chatgpt", "--add-account"])

    assert result.exit_code == 0, result.output
    assert calls == [{"enable_plan_use": True, "add_account": True}]
    assert "sign-in complete" in result.output.lower()


@pytest.mark.unit
def test_auth_login_reports_denied_authentication(monkeypatch):
    def denied(**_kwargs):
        raise chatgpt_auth.OAuthError("ChatGPT sign-in was denied.")

    monkeypatch.setattr(auth.chatgpt_auth, "sign_in", denied)

    result = runner.invoke(main.app, ["auth", "login", "--provider", "chatgpt"])

    assert result.exit_code == 1
    assert "sign-in was denied" in result.output
    assert "Traceback" not in result.output


@pytest.mark.unit
def test_auth_status_shows_account_permission_without_credentials(monkeypatch):
    account = chatgpt_auth.SavedAccount(
        client_id="issued-client-secretish",
        issuer="https://auth.openai.com",
        subject="private-subject",
        email="private@example.test",
        inference_enabled=False,
        requires_reauthorization=False,
    )
    monkeypatch.setattr(auth.chatgpt_auth, "saved_accounts", lambda: (account,))
    monkeypatch.setattr(
        auth.chatgpt_auth,
        "pinned_session",
        lambda: SimpleNamespace(registration=SimpleNamespace(client_id=account.client_id)),
    )

    result = runner.invoke(main.app, ["auth", "status", "--provider", "chatgpt"])

    assert result.exit_code == 0, result.output
    assert "selected" in result.output
    assert "plan use disabled" in result.output
    assert "private-subject" not in result.output
    assert "private@example.test" not in result.output
    assert "token" not in result.output.lower()


@pytest.mark.unit
def test_auth_status_reports_empty_state(monkeypatch):
    monkeypatch.setattr(auth.chatgpt_auth, "saved_accounts", lambda: ())

    result = runner.invoke(main.app, ["auth", "status", "--provider", "chatgpt"])

    assert result.exit_code == 0, result.output
    assert "not signed in" in result.output


@pytest.mark.unit
def test_auth_logout_clears_locally_when_remote_revocation_fails(monkeypatch):
    monkeypatch.setattr(
        auth.chatgpt_auth,
        "logout",
        lambda: chatgpt_auth.LogoutResult("issued-client", False),
    )

    result = runner.invoke(main.app, ["auth", "logout", "--provider", "chatgpt"])

    assert result.exit_code == 0, result.output
    assert "cleared locally" in result.output


@pytest.mark.unit
def test_auth_group_rejects_unknown_provider():
    result = runner.invoke(main.app, ["auth", "status", "--provider", "openai"])

    assert result.exit_code == 2
    assert "Only --provider chatgpt" in result.output


@pytest.mark.unit
def test_chatgpt_key_mapping_skips_password_prompt(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with patch.object(prompts.questionary, "password") as password:
        assert prompts.ensure_api_key("chatgpt") is None
    password.assert_not_called()


@pytest.mark.unit
def test_interactive_account_choice_returns_saved_inference_account(monkeypatch):
    account = chatgpt_auth.SavedAccount(
        client_id="issued-client",
        issuer="https://auth.openai.com",
        subject="subject",
        email=None,
        inference_enabled=True,
        requires_reauthorization=False,
    )
    monkeypatch.setattr(chatgpt_auth, "saved_accounts", lambda: (account,))
    with patch.object(prompts.questionary, "select") as select:
        select.return_value.ask.return_value = account.client_id
        chosen = prompts.select_chatgpt_account()

    assert chosen == account.client_id


@pytest.mark.unit
def test_headless_chatgpt_without_grant_names_explicit_login(monkeypatch, capsys):
    for key, value in {
        "TRADINGAGENTS_OUTPUT_LANGUAGE": "English",
        "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "1",
        "TRADINGAGENTS_MAX_RISK_ROUNDS": "1",
        "TRADINGAGENTS_LLM_PROVIDER": "chatgpt",
        "TRADINGAGENTS_QUICK_THINK_LLM": "model",
    }.items():
        monkeypatch.setenv(key, value)
    def no_session():
        raise chatgpt_auth.OAuthError("No ChatGPT account is signed in.")

    monkeypatch.setattr(chatgpt_auth, "pinned_session", no_session)

    gaps = selections.unattended_gaps(
        {"ticker": "NVDA", "date": "2026-10-03", "analysts": "market", "save": True, "show": False}
    )

    assert "tradingagents auth login --provider chatgpt" in gaps[0]
    assert capsys.readouterr().out == ""


@pytest.mark.unit
def test_missing_chatgpt_grant_stops_headless_account_selection(monkeypatch):
    def no_session():
        raise chatgpt_auth.OAuthError("No ChatGPT account is signed in.")

    monkeypatch.setattr(chatgpt_auth, "pinned_session", no_session)

    with pytest.raises(typer.Exit) as caught:
        selections.chatgpt_auth_account_for_headless()

    assert caught.value.exit_code == 1


@pytest.mark.unit
def test_selected_chatgpt_account_flows_into_run_config():
    selected = {
        "llm_provider": "chatgpt",
        "chatgpt_account_id": "issued-client",
        "quick_think_llm": "model",
        "deep_think_llm": "model",
        "backend_url": None,
        "research_depth": 1,
    }

    config = _build_run_config(selected, None)

    assert config["chatgpt_account_id"] == "issued-client"
    assert "access_token" not in config and "refresh_token" not in config


@pytest.mark.unit
def test_bare_analysis_and_backtest_remain_registered():
    help_result = runner.invoke(main.app, ["--help"])
    assert help_result.exit_code == 0
    assert "auth" in help_result.output
    assert "backtest" in help_result.output
