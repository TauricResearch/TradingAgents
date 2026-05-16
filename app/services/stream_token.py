"""
Short-lived HMAC-signed tokens for SSE auth.

The browser `EventSource` API can't send custom headers, so the standard
service-to-service HMAC header pattern (used by app/auth.py for POSTs)
doesn't work for `/stream/{run_id}`. Industry-standard alternative:
short-lived signed tokens in query params. AWS CloudFront, Google Cloud
Streaming, and similar services use the same pattern.

Token shape:
    <base64url(payload_json)>.<hex(hmac_sha256(payload, secret))>

Payload:
    { "runId": "<uuid>", "exp": <unix_seconds> }

The Node side mints these tokens when the dashboard opens the live
progress page. Python verifies on `/stream/{run_id}?token=...`.

Treat this file as a python-temp-pro template — works for any
service-to-browser streaming auth pattern.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from app.config import settings


# Default token lifetime. 30 minutes is generous — long enough that
# slow analyses don't expire mid-stream, short enough that a leaked
# token has limited blast radius.
DEFAULT_TOKEN_TTL_SECONDS = 30 * 60


def mint(run_id: str, ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS) -> str:
    """
    Mint a token for the given run_id valid for `ttl_seconds` from now.

    Called from the Python side when we need to test SSE locally. In
    production, the Node-side dashboard mints these — the wire format
    is documented in SERVICE.md so the Node side can reproduce it.
    """
    payload = {"runId": run_id, "exp": int(time.time()) + ttl_seconds}
    return _encode(payload)


class TokenError(Exception):
    """Raised when a token is malformed, expired, or signature-invalid."""


def verify(token: str, expected_run_id: str) -> None:
    """
    Verify a token's signature, expiry, and runId match. Raises
    TokenError with a specific reason on any failure. Returns None on
    success.
    """
    if not token or "." not in token:
        raise TokenError("malformed token")

    payload_b64, sig = token.split(".", 1)
    expected_sig = _sign(payload_b64)
    if not hmac.compare_digest(expected_sig, sig):
        raise TokenError("signature mismatch")

    try:
        payload_bytes = base64.urlsafe_b64decode(_pad(payload_b64))
        payload = json.loads(payload_bytes)
    except Exception:
        raise TokenError("payload decode failed")

    if not isinstance(payload, dict):
        raise TokenError("payload not an object")

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        raise TokenError("token expired")

    if payload.get("runId") != expected_run_id:
        raise TokenError("runId mismatch")


# ── Internal ──────────────────────────────────────────────────────────────

def _encode(payload: dict) -> str:
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii").rstrip("=")
    sig = _sign(payload_b64)
    return f"{payload_b64}.{sig}"


def _sign(payload_b64: str) -> str:
    secret = settings.HMAC_SHARED_SECRET.encode("utf-8")
    return hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()


def _pad(b64: str) -> bytes:
    """Restore the padding base64.urlsafe_b64decode requires."""
    return (b64 + "=" * (-len(b64) % 4)).encode("ascii")
