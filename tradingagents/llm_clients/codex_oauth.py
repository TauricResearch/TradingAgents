"""Helpers for ChatGPT OAuth used by the OpenAI Codex provider."""

from __future__ import annotations

from dataclasses import dataclass


class CodexOAuthUnavailableError(RuntimeError):
    """Raised when LangChain's ChatGPT OAuth helpers are unavailable."""


class CodexOAuthMissingTokenError(RuntimeError):
    """Raised when no ChatGPT OAuth token is available."""


@dataclass(frozen=True)
class ChatGPTOAuthStatus:
    account_id: str | None
    plan_type: str | None
    user_id: str | None


def get_chatgpt_oauth_status() -> ChatGPTOAuthStatus:
    """Return current ChatGPT OAuth status, refreshing the token if needed."""
    try:
        from langchain_openai.chatgpt_oauth import _FileChatGPTOAuthTokenProvider
    except (ImportError, ModuleNotFoundError) as exc:
        raise CodexOAuthUnavailableError(
            "ChatGPT sign-in requires langchain-openai>=1.3.3."
        ) from exc

    try:
        token = _FileChatGPTOAuthTokenProvider.from_default_store().get_token()
    except FileNotFoundError as exc:
        raise CodexOAuthMissingTokenError(
            "No ChatGPT OAuth token found at ~/.langchain/chatgpt-auth.json."
        ) from exc

    return ChatGPTOAuthStatus(
        account_id=token.account_id,
        plan_type=token.plan_type,
        user_id=token.user_id,
    )


def login_chatgpt_oauth(*, device_code: bool = False):
    """Run LangChain's ChatGPT OAuth flow and return a fresh status."""
    try:
        from langchain_openai.chatgpt_oauth import login_chatgpt, login_chatgpt_device
    except (ImportError, ModuleNotFoundError) as exc:
        raise CodexOAuthUnavailableError(
            "ChatGPT sign-in requires langchain-openai>=1.3.3."
        ) from exc

    if device_code:
        login_chatgpt_device()
    else:
        login_chatgpt()
    return get_chatgpt_oauth_status()
