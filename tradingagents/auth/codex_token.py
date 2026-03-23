"""OpenAI Codex OAuth token reader with auto-refresh.

Reads credentials stored by the OpenAI Codex CLI at ~/.codex/auth.json.
Checks expiry and refreshes automatically via the OpenAI token endpoint
before returning a valid access token — the same pattern OpenClaw uses
with its auth-profiles.json token sink.

Token refresh invalidates the previous refresh token, so only one tool
should hold the Codex credentials at a time (same caveat as OpenClaw).
"""

import json
import time
from pathlib import Path
from typing import Optional

import requests

_AUTH_FILE = Path.home() / ".codex" / "auth.json"
_TOKEN_URL = "https://auth.openai.com/oauth/token"
# Refresh this many seconds before actual expiry to avoid edge-case failures.
_EXPIRY_BUFFER_SECS = 60


def _load_auth() -> Optional[dict]:
    """Load the Codex auth file, return None if missing or malformed."""
    if not _AUTH_FILE.exists():
        return None
    try:
        return json.loads(_AUTH_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _save_auth(data: dict) -> None:
    _AUTH_FILE.write_text(json.dumps(data, indent=2))


def _is_expired(auth: dict) -> bool:
    """Return True if the access token is expired (or close to expiring)."""
    expires = auth.get("expires_at") or auth.get("tokens", {}).get("expires_at")
    if expires is None:
        # Fall back to decoding the JWT exp claim.
        try:
            import base64
            token = auth["tokens"]["access_token"]
            payload = token.split(".")[1]
            decoded = json.loads(base64.b64decode(payload + "=="))
            expires = decoded.get("exp")
        except Exception:
            return False  # Can't determine — assume valid.
    return time.time() >= (expires - _EXPIRY_BUFFER_SECS)


def _refresh(auth: dict) -> dict:
    """Exchange the refresh token for a new token pair and persist it."""
    refresh_token = auth["tokens"]["refresh_token"]
    resp = requests.post(
        _TOKEN_URL,
        json={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    new_tokens = resp.json()

    # Merge new tokens back into the auth structure and persist.
    auth["tokens"].update({
        "access_token": new_tokens["access_token"],
        "refresh_token": new_tokens.get("refresh_token", refresh_token),
        "expires_at": new_tokens.get("expires_in") and
                      int(time.time()) + int(new_tokens["expires_in"]),
    })
    auth["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _save_auth(auth)
    return auth


def get_codex_token() -> Optional[str]:
    """Return a valid OpenAI access token from the Codex CLI auth file.

    Resolution order:
      1. OPENAI_API_KEY environment variable (explicit key always wins)
      2. ~/.codex/auth.json — auto-refreshes if the access token is expired

    Returns None if no credentials are found.
    """
    import os
    explicit = os.environ.get("OPENAI_API_KEY")
    if explicit:
        return explicit

    auth = _load_auth()
    if not auth or "tokens" not in auth:
        return None

    # Refresh if expired.
    if _is_expired(auth):
        try:
            auth = _refresh(auth)
        except Exception:
            # Refresh failed — return whatever token we have and let the
            # API call surface a clearer error.
            pass

    return auth["tokens"].get("access_token")
