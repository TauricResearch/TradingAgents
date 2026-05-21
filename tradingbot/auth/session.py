"""
Cross-refresh session persistence for the Streamlit dashboard.

Approach
--------
- Sign a small token with HMAC-SHA256 (username + expiry + server secret).
- Store the token in a browser cookie (`ta_session`) via JS injection so it
  survives page reloads and new tabs in the same browser.
- On every page render, read `st.context.cookies` to rehydrate
  `st.session_state["auth_user"]` if a valid token is present.

Secret lives at ~/.tradingagents/session_secret (chmod 600, auto-created).
Override file location via TRADINGBOT_SESSION_SECRET_PATH or the secret
itself via TRADINGBOT_SESSION_SECRET.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

logger = logging.getLogger(__name__)

_COOKIE_NAME = "ta_session"
_DEFAULT_TTL_SECONDS = 7 * 24 * 3600   # 7 days


# ── Secret management ───────────────────────────────────────────────────────

def _secret_path() -> Path:
    p = os.environ.get(
        "TRADINGBOT_SESSION_SECRET_PATH",
        os.path.expanduser("~/.tradingagents/session_secret"),
    )
    return Path(p)


def _load_or_create_secret() -> bytes:
    override = os.environ.get("TRADINGBOT_SESSION_SECRET")
    if override:
        return override.encode("utf-8")

    path = _secret_path()
    if path.exists():
        return path.read_bytes()

    path.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_bytes(32)
    path.write_bytes(secret)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    logger.info("Generated session secret at %s", path)
    return secret


# ── Token format ────────────────────────────────────────────────────────────
# token := b64url(username) "." b64url(expiry_unix) "." b64url(hmac)

def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def make_token(username: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> str:
    secret = _load_or_create_secret()
    expiry = int(time.time()) + ttl_seconds
    msg = f"{username}|{expiry}".encode("utf-8")
    sig = hmac.new(secret, msg, hashlib.sha256).digest()
    return ".".join([
        _b64e(username.encode("utf-8")),
        _b64e(str(expiry).encode("ascii")),
        _b64e(sig),
    ])


def verify_token(token: str) -> Optional[str]:
    """Return username if valid+unexpired, else None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        username = _b64d(parts[0]).decode("utf-8")
        expiry = int(_b64d(parts[1]).decode("ascii"))
        sig = _b64d(parts[2])
    except (ValueError, UnicodeDecodeError):
        return None

    if expiry < time.time():
        return None

    secret = _load_or_create_secret()
    expected = hmac.new(
        secret, f"{username}|{expiry}".encode("utf-8"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    return username


# ── Streamlit integration ───────────────────────────────────────────────────

def _set_cookie_js(token: str, max_age: int = _DEFAULT_TTL_SECONDS) -> None:
    """
    Inject JS that writes the cookie on the parent document.

    `st.markdown` strips <script> tags for safety — we have to use
    components.v1.html (an iframe) and target parent.document.cookie.
    """
    components.html(
        f"""
        <script>
          window.parent.document.cookie =
            "{_COOKIE_NAME}={token}; max-age={max_age}; path=/; SameSite=Lax";
        </script>
        """,
        height=0,
    )


def _clear_cookie_js() -> None:
    components.html(
        f"""
        <script>
          window.parent.document.cookie =
            "{_COOKIE_NAME}=; max-age=0; path=/; SameSite=Lax";
        </script>
        """,
        height=0,
    )


def _read_cookie() -> Optional[str]:
    """Read the session cookie from the inbound request headers."""
    try:
        cookies = st.context.cookies  # Streamlit ≥1.37
    except AttributeError:
        return None
    return cookies.get(_COOKIE_NAME) if cookies else None


def restore_session() -> Optional[str]:
    """
    Restore st.session_state['auth_user'] from the cookie if present and valid.
    Returns the restored username or None. Idempotent — safe to call on
    every render.
    """
    if st.session_state.get("auth_user"):
        return st.session_state["auth_user"]

    token = _read_cookie()
    if not token:
        return None
    username = verify_token(token)
    if not username:
        return None
    st.session_state["auth_user"] = username
    return username


def save_session(username: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
    """Issue a fresh token and write it to the browser cookie."""
    token = make_token(username, ttl_seconds)
    _set_cookie_js(token, max_age=ttl_seconds)


def clear_session() -> None:
    """Clear the cookie and the in-process session_state entries."""
    _clear_cookie_js()
    for k in ("auth_user", "auth_mode", "_sidebar_opened"):
        st.session_state.pop(k, None)


def logout_and_redirect(login_url: str = "/login") -> None:
    """
    Hard-logout: clear cookie AND navigate the browser to `login_url`
    via a single iframe-injected script.

    st.switch_page would discard the cookie-clear iframe (Streamlit drops
    queued output when a rerun/navigation exception fires), so we bypass
    it and let the browser do a real navigation.

    Caller should `st.stop()` immediately after this returns to halt the
    rest of the current render — the queued iframe still gets flushed.
    """
    for k in ("auth_user", "auth_mode", "_sidebar_opened"):
        st.session_state.pop(k, None)
    components.html(
        f"""
        <script>
          window.parent.document.cookie =
            "{_COOKIE_NAME}=; max-age=0; path=/; SameSite=Lax";
          window.parent.location.href = "{login_url}";
        </script>
        """,
        height=0,
    )
