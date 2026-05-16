"""
HMAC signature verification middleware for service-to-service auth.

The Node-side worker (lyceum-fund/apps/worker) signs every POST request
to this service with:
    HMAC-SHA256("{timestamp}.{body}", HMAC_SHARED_SECRET)

Headers:
    X-Signature: sha256=<hex>
    X-Timestamp: <unix-seconds>

We verify both. Bad/missing/stale signatures return 401 without touching
the handler. Replay-protection window: ±5 minutes (clock-skew tolerance
between Vercel and Railway).

Skip paths:
    /health  — liveness probe (no PII to leak; healthcheckers don't sign)
    /ready   — readiness probe (same)
    /docs, /openapi.json, /redoc  — FastAPI's auto-generated docs (handy
                                    in dev; can be locked down later)

POSTs to anything else require a valid signature. GETs currently fall
through unauth — when SSE lands in TT-182c, /stream/{run_id} adds its
own session-JWT-based auth (browser EventSource can't sign HMAC).

Treat this file as a python-temp-pro template — the contract surface is
the same for any Node↔Python pair behind shared infrastructure.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.config import settings


logger = logging.getLogger(__name__)

# Routes that bypass signature verification entirely.
SKIP_PATHS = frozenset({"/health", "/ready", "/docs", "/openapi.json", "/redoc"})

# Maximum clock-skew between signer and verifier. 5 minutes is generous;
# tighten if we ever observe replay attempts.
MAX_TIMESTAMP_SKEW_SECONDS = 5 * 60


def compute_signature(timestamp: str, body: bytes, secret: str) -> str:
    """
    HMAC-SHA256 of `{timestamp}.{body}`. Returns the hex digest (no
    `sha256=` prefix — caller prepends as needed).
    """
    msg = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


class HMACAuthMiddleware(BaseHTTPMiddleware):
    """
    Verifies X-Signature on POST/PUT/PATCH/DELETE. Skip paths bypass.
    GET passes through unauth (route-level auth applies separately).
    """

    def __init__(self, app: ASGIApp, *, secret: str | None = None) -> None:
        super().__init__(app)
        # Allow override (tests inject a known secret); default to env.
        self._secret = secret or settings.HMAC_SHARED_SECRET

    async def dispatch(self, request: Request, call_next):
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        if request.method == "GET":
            # Read-only fall-through. Future GETs that need auth handle
            # it at the route level (e.g., session JWT for SSE).
            return await call_next(request)

        signature_header = request.headers.get("X-Signature", "")
        timestamp_header = request.headers.get("X-Timestamp", "")

        if not signature_header or not timestamp_header:
            return _unauth("missing signature or timestamp header")

        if not signature_header.startswith("sha256="):
            return _unauth("signature must be `sha256=<hex>`")

        # Timestamp skew check (replay protection).
        try:
            ts = int(timestamp_header)
        except ValueError:
            return _unauth("invalid timestamp")
        if abs(time.time() - ts) > MAX_TIMESTAMP_SKEW_SECONDS:
            return _unauth("timestamp outside allowed skew window")

        # Read body. Starlette caches request._body so downstream
        # handlers can re-read it via request.body() / .json().
        body = await request.body()

        expected = compute_signature(timestamp_header, body, self._secret)
        provided = signature_header[len("sha256="):]

        if not hmac.compare_digest(expected, provided):
            return _unauth("signature mismatch")

        return await call_next(request)


def _unauth(reason: str) -> JSONResponse:
    """Build a 401 response; log the reason for ops debugging."""
    logger.warning("HMAC auth rejected: %s", reason)
    return JSONResponse(
        status_code=401,
        content={"error": "unauthorized", "reason": reason},
    )
