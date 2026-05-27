"""OpenAI OAuth client — authenticate with ChatGPT Plus subscription via Device Code flow.

Use this provider when you have a ChatGPT Plus/Pro subscription but no API key.
The Device Code flow lets you authorize on any device (phone, laptop) without
sharing credentials with the server.

Usage
-----
1. Register an OAuth app at https://platform.openai.com/oauth
   → Obtain your client_id (e.g. "oauth-client-xxxxxxxxxxxxxxxx")
2. Set environment variables:

       TRADINGAGENTS_LLM_PROVIDER=openai-oauth
       OPENAI_OAUTH_CLIENT_ID=your-client-id-here
       # Optional — default scope works for ChatGPT Plus subscribers:
       # OPENAI_OAUTH_SCOPE=

3. Run TradingAgents — the first time it will show a URL + code.
   Open the URL, enter the code, approve → tokens cached for future runs.

Token flow
----------
    ┌─────────┐  1. device-code request    ┌──────────┐
    │         │ ──────────────────────────→ │          │
    │  Client │  2. device_code + user_code │  OpenAI  │
    │  (this) │ ←────────────────────────── │   Auth   │
    │         │  3. user opens URL, enters  │          │
    │         │     code, approves          │          │
    │         │  4. poll /token ──────────→ │          │
    │         │  5. access_token ←───────── │          │
    │         │  6. use token for API calls │          │
    └─────────┘                             └──────────┘

Refresh
-------
Tokens are cached in ~/.tradingagents/auth/openai-oauth/.
When the access token expires, the client auto-refreshes using the refresh token.
"""

from __future__ import annotations

import json
import os
import time
import warnings
from pathlib import Path
from typing import Any, Optional

import httpx
from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .openai_client import NormalizedChatOpenAI

# ── constants ────────────────────────────────────────────────────────────────

AUTH_BASE = "https://auth.openai.com"
API_BASE = "https://api.openai.com/v1"
TOKEN_CACHE_DIR = Path.home() / ".tradingagents" / "auth" / "openai-oauth"
DEFAULT_SCOPE = "openid email profile model.read model.write organization.read"
POLL_TIMEOUT = 600  # seconds to wait for user to authorize
POLL_INTERVAL = 5   # initial poll interval (server may override via interval field)

# httpx timeout for refresh and device-code requests (short — just auth calls)
_AUTH_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=5.0)

# ── helpers ──────────────────────────────────────────────────────────────────


def _ensure_dir() -> Path:
    TOKEN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Restrict permissions on macOS/Linux (no-op on Windows)
    try:
        TOKEN_CACHE_DIR.chmod(0o700)
    except Exception:
        pass
    return TOKEN_CACHE_DIR


def _token_path() -> Path:
    return _ensure_dir() / "tokens.json"


def _load_cached_tokens() -> Optional[dict[str, Any]]:
    path = _token_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Guard against stale/incomplete cache
        if "access_token" not in data:
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _save_tokens(data: dict[str, Any]) -> None:
    path = _token_path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except Exception:
        pass


def _clear_cached_tokens() -> None:
    path = _token_path()
    if path.exists():
        path.unlink()


# ── public: get an access token (cached or fresh) ────────────────────────────


def get_access_token(client_id: str, scope: str = DEFAULT_SCOPE) -> str:
    """Return a valid OpenAI access token.

    1. Check cache — if cached token is still valid, return it.
    2. If expired but refresh_token exists → refresh and cache.
    3. Otherwise — initiate Device Code flow.
    """
    cached = _load_cached_tokens()
    if cached:
        # Check expiry with a 60s safety margin
        expires_at = cached.get("expires_at", 0)
        if time.time() < expires_at - 60:
            return cached["access_token"]

        # Try refresh
        refresh = cached.get("refresh_token")
        if refresh:
            try:
                return _refresh_access_token(refresh)
            except Exception:
                _clear_cached_tokens()
                pass  # fall through to device flow

    # Full device-code authorization
    return _device_code_flow(client_id, scope)


def refresh_access_token(force: bool = False) -> Optional[str]:
    """Force-refresh the cached token (if refresh_token is available)."""
    cached = _load_cached_tokens()
    if not cached:
        return None
    refresh = cached.get("refresh_token")
    if not refresh:
        return None
    try:
        return _refresh_access_token(refresh)
    except Exception:
        _clear_cached_tokens()
        return None


# ── device-code flow ─────────────────────────────────────────────────────────


def _device_code_flow(client_id: str, scope: str) -> str:
    """Execute OAuth Device Code flow and return access_token."""
    import urllib.parse

    # Step 1: Request device code
    with httpx.Client(timeout=_AUTH_HTTP_TIMEOUT) as client:
        resp = client.post(
            f"{AUTH_BASE}/oauth/device",
            data={"client_id": client_id, "scope": scope},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Device code request failed (HTTP {resp.status_code}): "
                f"{resp.text[:200]}"
            )
        device_data = resp.json()

    device_code = device_data["device_code"]
    user_code = device_data["user_code"]
    verification_uri = device_data.get("verification_uri", "https://auth.openai.com/authorize")
    interval = device_data.get("interval", POLL_INTERVAL)

    # Step 2: Show user the code and URL
    print("\n" + "=" * 60, flush=True)
    print("  OpenAI OAuth Authorization Required", flush=True)
    print("=" * 60, flush=True)
    print(f"  1. Open:  {verification_uri}", flush=True)
    print(f"  2. Enter code:  {user_code}", flush=True)
    print(f"  3. Approve access for TradingAgents", flush=True)
    print(f"\n  Waiting up to {POLL_TIMEOUT // 60} minutes...", flush=True)
    print("=" * 60 + "\n", flush=True)

    # Step 3: Poll for authorization
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        time.sleep(int(interval))
        with httpx.Client(timeout=_AUTH_HTTP_TIMEOUT) as client:
            resp = client.post(
                f"{AUTH_BASE}/oauth/token",
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": client_id,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code == 200:
            token_data = resp.json()
            _cache_token_data(token_data)
            print("  ✅ Authorization successful!\n", flush=True)
            return token_data["access_token"]
        elif resp.status_code == 400:
            err = resp.json()
            error = err.get("error", "")
            if error == "authorization_pending":
                continue  # user hasn't approved yet — keep polling
            elif error == "slow_down":
                interval = min(interval * 2, 30)  # back off
                continue
            elif error in ("access_denied", "expired_token"):
                raise RuntimeError(
                    f"Authorization {error}. Run again to retry."
                )
        else:
            raise RuntimeError(
                f"Token poll failed (HTTP {resp.status_code}): {resp.text[:200]}"
            )

    raise TimeoutError(
        f"Authorization timed out after {POLL_TIMEOUT // 60} minutes. "
        "Run again to retry."
    )


# ── token refresh ────────────────────────────────────────────────────────────


def _refresh_access_token(refresh_token: str, client_id: Optional[str] = None) -> str:
    """Exchange a refresh token for a new access token."""
    # If client_id wasn't provided, try the cached config
    if not client_id:
        cached = _load_cached_tokens()
        if cached:
            client_id = cached.get("client_id")
    if not client_id:
        client_id = os.environ.get("OPENAI_OAUTH_CLIENT_ID", "")

    with httpx.Client(timeout=_AUTH_HTTP_TIMEOUT) as client:
        resp = client.post(
            f"{AUTH_BASE}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Token refresh failed (HTTP {resp.status_code}): {resp.text[:200]}"
        )
    token_data = resp.json()
    _cache_token_data(token_data)
    return token_data["access_token"]


def _cache_token_data(token_data: dict[str, Any]) -> None:
    """Store token data with an expiry timestamp."""
    expires_in = token_data.get("expires_in", 3600)
    token_data["expires_at"] = time.time() + expires_in
    # Store the client_id alongside for refresh
    if "client_id" not in token_data:
        token_data["client_id"] = os.environ.get("OPENAI_OAUTH_CLIENT_ID", "")
    _save_tokens(token_data)


# ── httpx auth middleware ────────────────────────────────────────────────────


def _make_oauth_http_client(client_id: str) -> httpx.Client:
    """Create an httpx.Client that injects the OAuth Bearer token.

    On 401, it tries a refresh and retries the request once.
    """
    token = get_access_token(client_id)

    class OAuthTransport(httpx.BaseTransport):
        """Transport that wraps the default httpx transport with OAuth."""

        def __init__(self):
            self._inner = httpx.HTTPTransport()

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal token
            request.headers["Authorization"] = f"Bearer {token}"
            request.headers["Content-Type"] = "application/json"
            response = self._inner.handle_request(request)

            # Token might be expired — attempt refresh and retry once
            if response.status_code == 401:
                try:
                    token = refresh_access_token() or get_access_token(client_id)
                except Exception:
                    pass  # refresh failed; return original error
                else:
                    request.headers["Authorization"] = f"Bearer {token}"
                    response = self._inner.handle_request(request)

            return response

        def close(self):
            self._inner.close()

    return httpx.Client(transport=OAuthTransport(), timeout=httpx.Timeout(300.0))


# ── OpenAI‑compatible LLM client ─────────────────────────────────────────────


class OpenAIOAuthChatOpenAI(NormalizedChatOpenAI):
    """ChatOpenAI subclass that injects OAuth token via a custom httpx client."""

    @classmethod
    def from_oauth(
        cls, model: str, client_id: str, **kwargs
    ) -> "OpenAIOAuthChatOpenAI":
        """Create an instance with OAuth token injection."""
        http_client = _make_oauth_http_client(client_id)
        return cls(model=model, http_client=http_client, **kwargs)

    def __init__(self, **kwargs):
        # Ensure we always use the standard chat completions endpoint
        kwargs.setdefault("base_url", API_BASE)
        super().__init__(**kwargs)


class OpenAIOAuthClient(BaseLLMClient):
    """Client for OpenAI via OAuth (ChatGPT Plus subscription).

    Uses the Device Code flow so you can authorize with your OpenAI credentials
    without sharing an API key.  Tokens are cached and auto-refreshed.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = "openai-oauth"
        self.client_id = (
            kwargs.get("client_id")
            or os.environ.get("OPENAI_OAUTH_CLIENT_ID")
            or self._prompt_client_id()
        )
        self._scope = kwargs.get("scope") or os.environ.get(
            "OPENAI_OAUTH_SCOPE", DEFAULT_SCOPE
        )

    @staticmethod
    def _prompt_client_id() -> str:
        print(
            "\nOpenAI OAuth requires a client_id.\n"
            "Register an OAuth app at https://platform.openai.com/oauth\n"
            "Then set OPENAI_OAUTH_CLIENT_ID in your .env file.\n",
            flush=True,
        )
        return os.environ.get("OPENAI_OAUTH_CLIENT_ID", "")

    def get_llm(self) -> Any:
        """Return configured OpenAIOAuthChatOpenAI instance."""
        if not self.client_id:
            raise ValueError(
                "OPENAI_OAUTH_CLIENT_ID is required. "
                "Set it in your .env or pass as client_id kwarg."
            )

        # Force token acquisition so the user sees the device-code prompt
        # right away rather than on the first LLM call.
        print("Initializing OpenAI OAuth...", flush=True)
        get_access_token(self.client_id, self._scope)

        return OpenAIOAuthChatOpenAI.from_oauth(
            model=self.model,
            client_id=self.client_id,
            base_url=self.base_url or API_BASE,
        )

    def validate_model(self) -> bool:
        """Allow any model — OpenAI will reject invalid ones."""
        return True

    def provide_auth_instructions(self) -> str:
        """Return setup instructions for the user."""
        return (
            "To use OpenAI OAuth:\n"
            "1. Go to https://platform.openai.com/oauth → create an app\n"
            "2. Copy your client_id\n"
            "3. Set OPENAI_OAUTH_CLIENT_ID=your-client-id in .env\n"
            "4. On first run, you'll be prompted to authorize via browser"
        )
