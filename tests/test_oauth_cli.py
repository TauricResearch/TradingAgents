"""Test integrazione CLI per openai-oauth: dropdown provider e auto-login."""
import pytest

from cli import utils as cli_utils
from tradingagents.llm_clients.oauth import OAuthNotLoggedIn


def test_provider_dropdown_includes_oauth(monkeypatch):
    captured = {}

    class FakeQ:
        def ask(self):
            return ("openai-oauth", None)

    def fake_select(message, choices=None, **kwargs):
        captured["choices"] = choices
        return FakeQ()

    monkeypatch.setattr(cli_utils.questionary, "select", fake_select)
    provider, url = cli_utils.select_llm_provider()
    assert provider == "openai-oauth"
    titles = [c.title for c in captured["choices"]]
    assert any("ChatGPT OAuth" in t for t in titles)


def test_ensure_oauth_login_noop_for_other_providers():
    assert cli_utils.ensure_oauth_login("openai") is None
    assert cli_utils.ensure_oauth_login("anthropic") is None


def test_ensure_oauth_login_returns_existing_token(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(cli_utils, "ensure_token", lambda: sentinel)
    assert cli_utils.ensure_oauth_login("openai-oauth") is sentinel


def test_ensure_oauth_login_triggers_login_when_missing(monkeypatch):
    called = {"login": 0}

    def fake_ensure_token():
        raise OAuthNotLoggedIn("no token")

    class Tok:
        account_id = "acct_1"

    def fake_login(**kwargs):
        called["login"] += 1
        return Tok()

    monkeypatch.setattr(cli_utils, "ensure_token", fake_ensure_token)
    monkeypatch.setattr(cli_utils, "oauth_login", fake_login)
    result = cli_utils.ensure_oauth_login("openai-oauth")
    assert called["login"] == 1
    assert result.account_id == "acct_1"


def test_select_model_filters_to_available_for_oauth(monkeypatch):
    captured = {}

    class FakeQ:
        def ask(self):
            return "gpt-5.4-mini"

    def fake_select(message, choices=None, **kwargs):
        captured["values"] = [c.value for c in choices]
        return FakeQ()

    monkeypatch.setattr(cli_utils.questionary, "select", fake_select)
    # solo gpt-5.4-mini è "disponibile"
    monkeypatch.setattr(cli_utils, "_oauth_available_model_ids", lambda refresh=False: {"gpt-5.4-mini"})
    cli_utils._select_model("openai-oauth", "quick")
    # gpt-5.3-codex / gpt-5.2 (non disponibili) filtrati via
    assert "gpt-5.4-mini" in captured["values"]
    assert "gpt-5.3-codex" not in captured["values"]
    assert "gpt-5.2" not in captured["values"]


def test_select_model_shows_full_catalog_when_discovery_fails(monkeypatch):
    captured = {}

    class FakeQ:
        def ask(self):
            return "gpt-5.4-mini"

    monkeypatch.setattr(cli_utils.questionary, "select",
                        lambda message, choices=None, **k: captured.update(values=[c.value for c in choices]) or FakeQ())
    monkeypatch.setattr(cli_utils, "_oauth_available_model_ids", lambda refresh=False: None)
    cli_utils._select_model("openai-oauth", "deep")
    # fallback: catalogo completo (include i modelli Plus/Pro)
    assert "gpt-5.3-codex" in captured["values"]


def test_ensure_oauth_login_exits_on_login_failure(monkeypatch):
    def fake_ensure_token():
        raise OAuthNotLoggedIn("no token")

    def fake_login(**kwargs):
        raise cli_utils.OAuthError("boom")

    monkeypatch.setattr(cli_utils, "ensure_token", fake_ensure_token)
    monkeypatch.setattr(cli_utils, "oauth_login", fake_login)
    with pytest.raises(SystemExit):
        cli_utils.ensure_oauth_login("openai-oauth")
