"""OpenAI-compatible LLM clients (OpenAI, xAI, OpenRouter, Ollama).

OpenAI auth resolution order:
  1. ``api_key`` kwarg (explicit key always wins)
  2. ``OPENAI_API_KEY`` environment variable
  3. ``~/.codex/auth.json`` — OpenAI Codex CLI OAuth token (auto-refreshed)
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import requests
from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

# ---------------------------------------------------------------------------
# Codex OAuth token reader (inlined from auth/codex_token.py)
# ---------------------------------------------------------------------------

_CODEX_AUTH_FILE = Path.home() / ".codex" / "auth.json"
_CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"
_EXPIRY_BUFFER_SECS = 60


def _load_codex_auth() -> Optional[dict]:
    if not _CODEX_AUTH_FILE.exists():
        return None
    try:
        return json.loads(_CODEX_AUTH_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _codex_token_expired(auth: dict) -> bool:
    expires = auth.get("expires_at") or auth.get("tokens", {}).get("expires_at")
    if expires is None:
        try:
            import base64
            token = auth["tokens"]["access_token"]
            payload = token.split(".")[1]
            decoded = json.loads(base64.b64decode(payload + "=="))
            expires = decoded.get("exp")
        except Exception:
            return False
    return time.time() >= (expires - _EXPIRY_BUFFER_SECS)


def _refresh_codex_token(auth: dict) -> dict:
    refresh_token = auth["tokens"]["refresh_token"]
    resp = requests.post(
        _CODEX_TOKEN_URL,
        json={"grant_type": "refresh_token", "refresh_token": refresh_token},
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    new_tokens = resp.json()
    auth["tokens"].update({
        "access_token": new_tokens["access_token"],
        "refresh_token": new_tokens.get("refresh_token", refresh_token),
        "expires_at": new_tokens.get("expires_in") and int(time.time()) + int(new_tokens["expires_in"]),
    })
    auth["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _CODEX_AUTH_FILE.write_text(json.dumps(auth, indent=2))
    return auth


def _get_codex_token() -> Optional[str]:
    """Return a valid OpenAI token from OPENAI_API_KEY or ~/.codex/auth.json."""
    explicit = os.environ.get("OPENAI_API_KEY")
    if explicit:
        return explicit
    auth = _load_codex_auth()
    if not auth or "tokens" not in auth:
        return None
    if _codex_token_expired(auth):
        try:
            auth = _refresh_codex_token(auth)
        except Exception:
            pass
    return auth["tokens"].get("access_token")


# ---------------------------------------------------------------------------
# OpenAI-compatible client
# ---------------------------------------------------------------------------

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client",
)

_PROVIDER_CONFIG = {
    "xai":        ("https://api.x.ai/v1",            "XAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1",   "OPENROUTER_API_KEY"),
    "ollama":     ("http://localhost:11434/v1",       None),
}


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output.

    The Responses API returns content as a list of typed blocks
    (reasoning, text, etc.). This normalizes to string for consistent
    downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI, xAI, OpenRouter, and Ollama providers.

    For native OpenAI models, uses the Responses API (/v1/responses) which
    supports reasoning_effort with function tools across all model families
    (GPT-4.1, GPT-5). Third-party compatible providers (xAI, OpenRouter,
    Ollama) use standard Chat Completions.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance."""
        llm_kwargs = {"model": self.model}

        if self.provider in _PROVIDER_CONFIG:
            base_url, api_key_env = _PROVIDER_CONFIG[self.provider]
            llm_kwargs["base_url"] = base_url
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
            else:
                llm_kwargs["api_key"] = "ollama"
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        if self.provider == "openai":
            llm_kwargs["use_responses_api"] = True
            if "api_key" not in llm_kwargs:
                token = _get_codex_token()
                if token:
                    llm_kwargs["api_key"] = token

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model(self.provider, self.model)

