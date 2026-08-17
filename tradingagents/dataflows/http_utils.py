"""HTTP helpers that keep API keys out of error messages.

FRED and Alpha Vantage both authenticate with a query parameter, so every
``requests`` exception they raise stringifies to include the full request URL —
key and all. Those strings do not stay in the process: they are logged, returned
to the model as the ``DATA_UNAVAILABLE:`` sentinel for optional categories
(``macro_data`` is FRED), and passed straight to the LLM by the indicators tool,
which puts them in ``message_tool.log`` and the saved markdown report.

Neither vendor accepts the key in a header, so the fix is at the boundary:
route requests through :func:`request_get` and status checks through
:func:`raise_for_status`, both of which re-raise with the secret masked.
"""
from __future__ import annotations

import re

import requests

# Query parameters whose value is a credential. Matched case-insensitively, so
# ``apiKey`` and ``API_KEY`` are covered too.
SENSITIVE_QUERY_PARAMS = (
    "api_key",
    "apikey",
    "access_token",
    "auth_token",
    "token",
    "secret",
    "password",
    "signature",
    "key",
)

REDACTED = "***REDACTED***"

# Match ``?param=value`` / ``&param=value`` anywhere in free text, not just in a
# parsable URL: the leaks come from exception messages, where the URL is already
# embedded in prose ("... for url: https://...").
_SENSITIVE_RE = re.compile(
    r"(?i)([?&](?:" + "|".join(SENSITIVE_QUERY_PARAMS) + r")=)([^&\s\"'>]*)"
)


def redact_secrets(text: str) -> str:
    """Mask credential-bearing query parameter values in ``text``."""
    return _SENSITIVE_RE.sub(lambda m: m.group(1) + REDACTED, text)


def _redacted_copy(exc: Exception) -> Exception:
    """Rebuild ``exc`` with its message redacted, preserving the type."""
    message = redact_secrets(str(exc))
    try:
        return type(exc)(
            message,
            response=getattr(exc, "response", None),
            request=getattr(exc, "request", None),
        )
    except TypeError:
        # A subclass with a different signature; the type matters less than
        # never re-raising the unredacted message.
        return requests.RequestException(message)


def raise_for_status(response: requests.Response) -> None:
    """``response.raise_for_status()`` with the URL's secrets masked.

    Raised ``from None``: chaining would keep the original, unredacted message
    reachable via ``__cause__`` and print it in any traceback.
    """
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise _redacted_copy(exc) from None


def request_get(url: str, **kwargs) -> requests.Response:
    """``requests.get`` with secrets masked in any transport-level failure.

    Connection, timeout and SSL errors embed the full URL in their message just
    as HTTP errors do, so the call itself needs wrapping — not only the status
    check.
    """
    try:
        return requests.get(url, **kwargs)
    except requests.RequestException as exc:
        raise _redacted_copy(exc) from None
