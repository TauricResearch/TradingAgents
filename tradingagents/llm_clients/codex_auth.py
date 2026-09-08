"""Resolve a usable credential for the ChatGPT-subscription Codex endpoint.

That endpoint authenticates with a short-lived OAuth bearer token plus an
account id, both stored by the official Codex client in ``~/.codex/auth.json``.
This module reads that file and refreshes the token when it is close to expiry,
writing the rotated tokens back: the refresh token rotates on every refresh, so
refreshing without persisting would invalidate the copy the Codex client holds
and silently log the user out of it.
"""

from __future__ import annotations

import base64
import contextlib
import datetime as dt
import json
import os
import stat
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no fcntl
    fcntl = None

DEFAULT_AUTH_PATH = "~/.codex/auth.json"
TOKEN_URL = "https://auth.openai.com/oauth/token"
# Codex's public OAuth client id. Only used when the stored id_token carries no
# readable ``aud`` claim to take it from.
FALLBACK_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
# Refresh this far ahead of expiry so a long run cannot begin with a token that
# dies part-way through.
REFRESH_MARGIN_SECONDS = 300


class CodexAuthError(RuntimeError):
    """Raised when no usable Codex credential can be produced."""


@dataclass(frozen=True)
class CodexCredentials:
    """A bearer token and the account it belongs to."""

    token: str
    account_id: str

    @property
    def headers(self) -> dict[str, str]:
        """Extra request headers the Codex endpoint requires.

        The bearer token is passed separately as the client's api_key; only the
        account routing and the beta opt-in belong here.
        """
        return {
            "chatgpt-account-id": self.account_id,
            "OpenAI-Beta": "responses=experimental",
        }


def _auth_path(auth_path: str | None) -> Path:
    raw = (
        auth_path
        or os.environ.get("TRADINGAGENTS_CODEX_AUTH_PATH")
        or DEFAULT_AUTH_PATH
    )
    return Path(raw).expanduser()


def _jwt_claims(token: str) -> dict:
    """Decode a JWT payload without verifying its signature.

    Only ``exp`` (to decide whether to refresh) and ``aud`` (the OAuth client
    id) are read. The server remains the authority on validity, so an opaque or
    malformed token simply reports no claims.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, TypeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _is_expiring(token: str, now: float) -> bool:
    """Whether ``token`` is expired or close enough to expiry to replace."""
    try:
        return float(_jwt_claims(token).get("exp")) - now <= REFRESH_MARGIN_SECONDS
    except (TypeError, ValueError):
        # An unreadable expiry is treated as expiring: better one wasted refresh
        # than a run that dies on the first call.
        return True


def _client_id(id_token: str | None) -> str:
    audience = _jwt_claims(id_token or "").get("aud")
    if isinstance(audience, list) and audience:
        return str(audience[0])
    if isinstance(audience, str) and audience:
        return audience
    return FALLBACK_CLIENT_ID


def _read_auth(path: Path) -> dict:
    try:
        with path.open() as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise CodexAuthError(
            f"No Codex credentials at {path}. Sign in with the Codex app or CLI "
            "first, or point TRADINGAGENTS_CODEX_AUTH_PATH at your auth.json."
        ) from exc
    except json.JSONDecodeError as exc:
        raise CodexAuthError(
            f"Codex credentials at {path} are not valid JSON. Sign in again with "
            "the Codex app or CLI."
        ) from exc


def _refresh(refresh_token: str, client_id: str) -> dict:
    """Exchange a refresh token for a new token set."""
    body = json.dumps(
        {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "openid profile email",
        }
    ).encode()
    request = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise CodexAuthError(
            f"Codex token refresh was rejected (HTTP {exc.code}). The stored "
            "refresh token is no longer valid — sign in again with the Codex "
            "app or CLI."
        ) from exc
    except urllib.error.URLError as exc:
        raise CodexAuthError(
            f"Codex token refresh could not reach {TOKEN_URL}: {exc.reason}"
        ) from exc


def _write_auth(path: Path, auth: dict) -> None:
    """Replace the auth file atomically, preserving its permissions."""
    mode = stat.S_IMODE(path.stat().st_mode)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w") as handle:
        json.dump(auth, handle, indent=2)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


@contextlib.contextmanager
def _refresh_lock(path: Path):
    """Serialise refresh-and-write across concurrent runs.

    Windows has no ``fcntl``; there this degrades to a no-op. The atomic
    ``os.replace`` still rules out a torn file, so only a redundant double
    refresh becomes possible.
    """
    if fcntl is None:
        yield
        return
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _credentials(tokens: dict) -> CodexCredentials:
    return CodexCredentials(
        token=tokens["access_token"], account_id=tokens["account_id"]
    )


def _validated_tokens(auth: dict, path: Path) -> dict:
    """Return the token bundle, or explain what is missing.

    Applied to every read of the file, not just the first: ``resolve`` reads
    once to decide whether to refresh and again under the lock, and the official
    Codex client may rewrite the file in between. Without this the second read
    would surface a bare ``KeyError``.
    """
    tokens = auth.get("tokens") or {}
    if not tokens.get("access_token") or not tokens.get("account_id"):
        raise CodexAuthError(
            f"Codex credentials at {path} are missing an access token or an "
            "account id. Sign in again with the Codex app or CLI."
        )
    return tokens


def _require_refresh_token(tokens: dict, path: Path) -> None:
    """Fail with guidance when an expired token cannot be renewed."""
    if not tokens.get("refresh_token"):
        raise CodexAuthError(
            f"The Codex access token in {path} has expired and no refresh token "
            "is stored. Sign in again with the Codex app or CLI."
        )


def resolve(auth_path: str | None = None) -> CodexCredentials:
    """Return a currently-valid Codex bearer token and account id."""
    path = _auth_path(auth_path)
    auth = _read_auth(path)

    if auth.get("auth_mode") != "chatgpt":
        raise CodexAuthError(
            f"Codex credentials at {path} use auth_mode "
            f"{auth.get('auth_mode')!r}, not 'chatgpt'. An API-key Codex install "
            "should use the 'openai' provider instead."
        )

    tokens = _validated_tokens(auth, path)
    if not _is_expiring(tokens["access_token"], time.time()):
        return _credentials(tokens)
    _require_refresh_token(tokens, path)

    with _refresh_lock(path):
        # Re-read under the lock: a concurrent run may already have refreshed,
        # in which case its token is the valid one and ours is already stale.
        # Re-validate as well — this is a fresh read of a file another process
        # may have rewritten, not the one checked above.
        auth = _read_auth(path)
        tokens = _validated_tokens(auth, path)
        if not _is_expiring(tokens["access_token"], time.time()):
            return _credentials(tokens)
        _require_refresh_token(tokens, path)

        fresh = _refresh(tokens["refresh_token"], _client_id(tokens.get("id_token")))
        tokens["access_token"] = fresh["access_token"]
        tokens["refresh_token"] = fresh.get("refresh_token") or tokens["refresh_token"]
        if fresh.get("id_token"):
            tokens["id_token"] = fresh["id_token"]
        auth["tokens"] = tokens
        auth["last_refresh"] = (
            dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        )
        _write_auth(path, auth)

    return _credentials(tokens)
