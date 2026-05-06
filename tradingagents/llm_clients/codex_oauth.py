"""OAuth helpers for ChatGPT/Codex subscription access."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import webbrowser
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests


CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
REDIRECT_URI = "http://localhost:1455/auth/callback"
DEVICE_REDIRECT_URI = "https://auth.openai.com/deviceauth/callback"
SCOPE = "openid profile email offline_access"
ACCOUNT_CLAIM = "https://api.openai.com/auth"
DEVICE_USER_CODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
DEVICE_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"


@dataclass
class CodexOAuthTokens:
    access_token: str
    refresh_token: str
    expires_at: float
    account_id: str | None = None
    id_token: str | None = None

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "CodexOAuthTokens":
        return cls(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload["refresh_token"]),
            expires_at=float(payload["expires_at"]),
            account_id=payload.get("account_id"),
            id_token=payload.get("id_token"),
        )


def default_token_path() -> Path:
    configured = os.getenv("TRADINGAGENTS_CODEX_OAUTH_FILE")
    if configured:
        return Path(configured).expanduser()
    return Path(os.getenv("TRADINGAGENTS_CACHE_DIR", "~/.tradingagents/cache")).expanduser() / "codex_oauth.json"


class CodexOAuthStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_token_path()

    def load(self) -> CodexOAuthTokens:
        if not self.path.exists():
            raise RuntimeError(
                "Codex OAuth is not configured. Run "
                "`python scripts/codex_oauth_login.py` first."
            )
        return CodexOAuthTokens.from_json(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, tokens: CodexOAuthTokens) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(tokens), indent=2), encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass


def decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload.encode()).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}


def extract_account_id(access_token: str) -> str | None:
    return extract_account_id_from_claims(decode_jwt_payload(access_token))


def extract_account_id_from_claims(payload: dict[str, Any]) -> str | None:
    claim = payload.get(ACCOUNT_CLAIM)
    candidates: list[Any] = []
    if isinstance(claim, dict):
        candidates.extend([
            claim.get("chatgpt_account_id"),
            claim.get("account_id"),
            claim.get("accountId"),
        ])
        organizations = claim.get("organizations")
        if isinstance(organizations, list) and organizations:
            first_org = organizations[0]
            if isinstance(first_org, dict):
                candidates.append(first_org.get("id"))
    candidates.extend([
        payload.get("chatgpt_account_id"),
        payload.get("account_id"),
        payload.get("accountId"),
    ])
    organizations = payload.get("organizations")
    if isinstance(organizations, list) and organizations:
        first_org = organizations[0]
        if isinstance(first_org, dict):
            candidates.append(first_org.get("id"))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def extract_account_id_from_tokens(access_token: str, id_token: str | None = None) -> str | None:
    if id_token:
        account_id = extract_account_id_from_claims(decode_jwt_payload(id_token))
        if account_id:
            return account_id
    return extract_account_id(access_token)


def refresh_tokens(refresh_token: str) -> CodexOAuthTokens:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Codex OAuth refresh failed: HTTP {response.status_code} {response.text}")
    payload = response.json()
    access = payload["access_token"]
    id_token = payload.get("id_token")
    return CodexOAuthTokens(
        access_token=access,
        refresh_token=payload["refresh_token"],
        expires_at=time.time() + int(payload["expires_in"]),
        account_id=extract_account_id_from_tokens(access, id_token),
        id_token=id_token,
    )


def get_valid_tokens(store: CodexOAuthStore | None = None) -> CodexOAuthTokens:
    store = store or CodexOAuthStore()
    tokens = store.load()
    if tokens.expires_at > time.time() + 60:
        if tokens.account_id is None:
            tokens.account_id = extract_account_id_from_tokens(tokens.access_token, tokens.id_token)
            store.save(tokens)
        return tokens
    refreshed = refresh_tokens(tokens.refresh_token)
    store.save(refreshed)
    return refreshed


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def create_authorization_url() -> tuple[str, str, str]:
    verifier, challenge = _pkce_pair()
    state = secrets.token_hex(16)
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": "opencode",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}", verifier, state


def exchange_authorization_code(code: str, verifier: str) -> CodexOAuthTokens:
    return exchange_authorization_code_for_redirect(code, verifier, REDIRECT_URI)


def exchange_authorization_code_for_redirect(
    code: str,
    verifier: str,
    redirect_uri: str,
) -> CodexOAuthTokens:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Codex OAuth exchange failed: HTTP {response.status_code} {response.text}")
    payload = response.json()
    access = payload["access_token"]
    id_token = payload.get("id_token")
    return CodexOAuthTokens(
        access_token=access,
        refresh_token=payload["refresh_token"],
        expires_at=time.time() + int(payload["expires_in"]),
        account_id=extract_account_id_from_tokens(access, id_token),
        id_token=id_token,
    )


def run_login_flow(
    store: CodexOAuthStore | None = None,
    open_browser: bool = True,
    timeout_seconds: int = 300,
) -> CodexOAuthTokens:
    store = store or CodexOAuthStore()
    url, verifier, expected_state = create_authorization_url()
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib callback name
            parsed = urlparse(self.path)
            if parsed.path != "/auth/callback":
                self.send_response(404)
                self.end_headers()
                return
            params = parse_qs(parsed.query)
            result["code"] = params.get("code", [""])[0]
            result["state"] = params.get("state", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body>TradingAgents Codex OAuth login complete. You can close this tab.</body></html>")

        def log_message(self, format, *args):  # noqa: A002, D401 - silence stdlib access log
            return

    print("Open this URL to sign in with ChatGPT/Codex:", flush=True)
    print(url, flush=True)
    if open_browser:
        webbrowser.open(url)

    try:
        server = HTTPServer(("127.0.0.1", 1455), Handler)
    except OSError as e:
        raise RuntimeError(f"Failed to start OAuth callback server on port 1455: {e}") from e
    server.timeout = 1
    deadline = time.time() + timeout_seconds
    while "code" not in result:
        if time.time() > deadline:
            raise RuntimeError("Timed out waiting for Codex OAuth callback.")
        server.handle_request()

    if result.get("state") != expected_state:
        raise RuntimeError("Codex OAuth state mismatch; refusing token exchange.")
    tokens = exchange_authorization_code(result["code"], verifier)
    store.save(tokens)
    return tokens


def run_device_login_flow(
    store: CodexOAuthStore | None = None,
    timeout_seconds: int = 300,
) -> CodexOAuthTokens:
    store = store or CodexOAuthStore()
    response = requests.post(
        DEVICE_USER_CODE_URL,
        json={"client_id": CLIENT_ID},
        headers={
            "Content-Type": "application/json",
            "User-Agent": "TradingAgents",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Failed to initiate Codex device authorization: HTTP {response.status_code} {response.text}")
    device_data = response.json()
    device_auth_id = device_data["device_auth_id"]
    user_code = device_data["user_code"]
    interval = max(int(device_data.get("interval") or 5), 1)

    print("Open this URL to sign in with ChatGPT/Codex:", flush=True)
    print("https://auth.openai.com/codex/device", flush=True)
    print(f"Enter code: {user_code}", flush=True)

    deadline = time.time() + timeout_seconds
    while time.time() <= deadline:
        token_response = requests.post(
            DEVICE_TOKEN_URL,
            json={
                "device_auth_id": device_auth_id,
                "user_code": user_code,
            },
            headers={
                "Content-Type": "application/json",
                "User-Agent": "TradingAgents",
            },
            timeout=30,
        )
        if token_response.status_code == 200:
            token_payload = token_response.json()
            tokens = exchange_authorization_code_for_redirect(
                token_payload["authorization_code"],
                token_payload["code_verifier"],
                DEVICE_REDIRECT_URI,
            )
            store.save(tokens)
            return tokens
        if token_response.status_code not in {403, 404}:
            raise RuntimeError(
                f"Codex device authorization failed: HTTP {token_response.status_code} {token_response.text}"
            )
        time.sleep(interval + 3)

    raise RuntimeError("Timed out waiting for Codex device authorization.")
