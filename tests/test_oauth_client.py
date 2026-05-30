"""Test del client openai-oauth: base_url Codex, header, streaming, store."""
import base64
import json
import time

import pytest

from tradingagents.llm_clients.openai_client import OpenAIClient
from tradingagents.llm_clients.oauth.store import OAuthTokenStore


def _jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.sig"


@pytest.fixture
def logged_in(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_OAUTH_PATH", str(tmp_path / "o.json"))
    OAuthTokenStore().save({
        "id_token": _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "acct_xyz"}}),
        "access_token": _jwt({"exp": int(time.time()) + 3600}),
        "refresh_token": "R",
    })


def test_oauth_client_targets_codex_backend(logged_in):
    llm = OpenAIClient("gpt-5.3-codex", provider="openai-oauth").get_llm()
    assert "chatgpt.com/backend-api/codex" in str(llm.openai_api_base)
    assert llm.use_responses_api is True
    assert llm.streaming is True


def test_oauth_client_sets_account_and_originator_headers(logged_in):
    llm = OpenAIClient("gpt-5.3-codex", provider="openai-oauth").get_llm()
    headers = llm.default_headers or {}
    assert headers.get("ChatGPT-Account-ID") == "acct_xyz"
    assert headers.get("originator") == "codex_cli_rs"


def test_oauth_client_requires_login(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_OAUTH_PATH", str(tmp_path / "missing.json"))
    from tradingagents.llm_clients.oauth import OAuthNotLoggedIn
    with pytest.raises(OAuthNotLoggedIn):
        OpenAIClient("gpt-5.3-codex", provider="openai-oauth").get_llm()


def test_oauth_client_sets_fedramp_and_residency_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_OAUTH_PATH", str(tmp_path / "o.json"))
    OAuthTokenStore().save({
        "id_token": _jwt({"https://api.openai.com/auth": {
            "chatgpt_account_id": "acct_fed",
            "chatgpt_account_is_fedramp": True,
            "chatgpt_data_residency": "us-gov",
        }}),
        "access_token": _jwt({"exp": int(time.time()) + 3600}),
        "refresh_token": "R",
    })
    llm = OpenAIClient("gpt-5.4-mini", provider="openai-oauth").get_llm()
    headers = llm.default_headers or {}
    assert headers.get("X-OpenAI-Fedramp") == "true"
    assert headers.get("x-openai-internal-codex-residency") == "us-gov"


def test_oauth_client_uses_codex_subclass(logged_in):
    from tradingagents.llm_clients.openai_client import CodexChatOpenAI
    llm = OpenAIClient("gpt-5.4-mini", provider="openai-oauth").get_llm()
    assert isinstance(llm, CodexChatOpenAI)
    assert llm.store is False
