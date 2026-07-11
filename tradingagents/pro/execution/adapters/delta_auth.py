"""Delta Exchange (India) request signing + credential hygiene.

Scheme (docs.delta.exchange): HMAC-SHA256 hex over
``method + timestamp + path + query + body`` with headers ``api-key``,
``signature``, ``timestamp``. Signatures expire **5 seconds** after the
timestamp — generate per request at send time, never pre-build, and
refuse to trade when local/venue clock skew exceeds the budget.

Credential hygiene: the key/secret must never appear in logs or error
text. Everything that might carry them passes through ``redact``.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

MAX_CLOCK_SKEW_SECONDS = 2.0


def redact(text: str, *secrets: str) -> str:
    """Blank every secret occurrence; safe on empty secrets."""
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***REDACTED***")
    return out


@dataclass(frozen=True)
class DeltaCredentials:
    api_key: str
    api_secret: str

    def __repr__(self) -> str:  # keys must not leak via repr/str either
        return "DeltaCredentials(api_key=***, api_secret=***)"

    __str__ = __repr__


def sign(credentials: DeltaCredentials, method: str, path: str,
         query: str = "", body: str = "",
         timestamp: int | None = None) -> dict[str, str]:
    """Build the three auth headers for one request. ``query`` includes
    the leading '?' when present (Delta prehash convention)."""
    ts = str(timestamp if timestamp is not None else int(time.time()))
    prehash = f"{method.upper()}{ts}{path}{query}{body}"
    signature = hmac.new(
        credentials.api_secret.encode(), prehash.encode(), hashlib.sha256
    ).hexdigest()
    return {
        "api-key": credentials.api_key,
        "signature": signature,
        "timestamp": ts,
    }


def clock_skew_seconds(response_date_header: str,
                       local_now: float | None = None) -> float:
    """Skew estimate from an HTTP ``Date`` header (Delta exposes no time
    endpoint). Positive = local clock ahead of venue. ~1s resolution —
    good enough against a 2s budget backed by NTP on the host."""
    venue = parsedate_to_datetime(response_date_header).timestamp()
    local = time.time() if local_now is None else local_now
    return local - venue
