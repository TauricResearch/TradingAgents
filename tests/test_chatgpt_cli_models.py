from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from cli import prefs, selections
from tradingagents.llm_clients import chatgpt_auth

ACCOUNT = "oaiapp_cli_account"


def _account_store(path: Path) -> None:
    state = chatgpt_auth._new_auth()
    state["accounts"][ACCOUNT] = {
        "client_id": ACCOUNT,
        "issuer": "https://auth.openai.com",
        "subject": "cli-account-subject",
        "inference_enabled": True,
        "email": None,
        "ext_agent_host_id": state["ext_agent_host_id"],
        "access_token": "cli-access",
        "refresh_token": "cli-refresh",
        "id_token": None,
        "scopes": ["openid", chatgpt_auth.PLAN_SCOPE],
        "expires_at": 4_102_444_800,
        "rotation_pending": False,
        "requires_reauthorization": False,
    }
    state["selected_client_id"] = ACCOUNT
    with chatgpt_auth._locked(path):
        chatgpt_auth._save(path, state)


@pytest.mark.unit
def test_headless_env_selection_uses_the_saved_chatgpt_account(monkeypatch, tmp_path: Path):
    auth_path = tmp_path / "auth.json"
    _account_store(auth_path)
    monkeypatch.setattr(chatgpt_auth, "_default_store_path", lambda: auth_path)
    values = {
        "TRADINGAGENTS_OUTPUT_LANGUAGE": "English",
        "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "1",
        "TRADINGAGENTS_MAX_RISK_ROUNDS": "1",
        "TRADINGAGENTS_LLM_PROVIDER": "chatgpt",
        "TRADINGAGENTS_QUICK_THINK_LLM": "quick-a",
        "TRADINGAGENTS_DEEP_THINK_LLM": "deep-a",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(selections.sys, "stdin", None)
    config = dict(
        selections.DEFAULT_CONFIG,
        llm_provider="chatgpt",
        quick_think_llm="quick-a",
        deep_think_llm="deep-a",
    )
    monkeypatch.setattr(selections, "DEFAULT_CONFIG", config)
    monkeypatch.setattr(selections, "fetch_announcements", lambda: [])
    monkeypatch.setattr(selections, "display_announcements", lambda *_args: None)
    def reject_implicit_sign_in(**_kwargs) -> None:
        raise AssertionError("headless sign-in opened")

    monkeypatch.setattr(chatgpt_auth, "sign_in", reject_implicit_sign_in)
    flags = {
        "ticker": "NVDA",
        "date": "2026-10-03",
        "analysts": "market",
        "save": True,
        "show": False,
    }

    result = selections._prompt_selections({}, flags)

    assert result["llm_provider"] == "chatgpt"
    assert result["chatgpt_account_id"] == ACCOUNT
    assert result["quick_think_llm"] == "quick-a"
    assert result["deep_think_llm"] == "deep-a"
    assert selections.unattended_gaps(flags) == []


@pytest.mark.unit
def test_chatgpt_preferences_preserve_unlisted_model_ids(
    monkeypatch, tmp_path: Path
):
    auth_path = tmp_path / "auth.json"
    _account_store(auth_path)
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "models": [
                    {"visibility": "list", "display_name": "Quick", "slug": "quick-a"},
                    {"visibility": "list", "display_name": "Deep", "slug": "deep-a"},
                ]
            },
        )

    transport = httpx.MockTransport(handle)
    original_pin = chatgpt_auth.pinned_session

    def pinned_session(*, client_id=None):
        return original_pin(
            store_path=auth_path, client_id=client_id, http_transport=transport
        )

    monkeypatch.setattr(chatgpt_auth, "pinned_session", pinned_session)

    kept = prefs.sanitize(
        {
            "llm_provider": "chatgpt",
            "chatgpt_account_id": ACCOUNT,
            "quick_think_llm": "quick-a",
            "deep_think_llm": "retired-model",
        },
        "stock",
    )

    assert kept["chatgpt_account_id"] == ACCOUNT
    assert kept["quick_think_llm"] == "quick-a"
    assert kept["deep_think_llm"] == "retired-model"
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer cli-access"
