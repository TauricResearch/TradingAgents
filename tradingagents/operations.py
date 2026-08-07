"""Small sanitized alerting controls for the production collector."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Mapping
from typing import Any
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "database_url",
    "dsn",
    "error",
    "exception",
    "password",
    "secret",
    "token",
    "traceback",
    "url",
)
_URL = re.compile(r"\b(?:https?|postgres(?:ql)?(?:\+[^:]+)?|redis)://\S+", re.IGNORECASE)
_BEARER = re.compile(r"\bBearer\s+\S+", re.IGNORECASE)
_API_KEY = re.compile(r"\b(?:sk|xox[baprs]|gh[pousr])-[A-Za-z0-9_-]{12,}\b")


def _redact_text(value: str) -> str:
    """Remove common credential-bearing strings without trying to classify secrets."""
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _API_KEY.sub("[REDACTED_KEY]", value)
    return _URL.sub("[REDACTED_URL]", value)


def redact_sensitive(value: Any, *, key: str | None = None) -> Any:
    """Return a JSON-safe copy with URLs, credentials, and exception text removed."""
    normalized_key = (key or "").strip().lower()
    if normalized_key and any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, BaseException):
        return {"exception_type": type(value).__name__}
    if isinstance(value, Mapping):
        redacted = {}
        for child_key, child_value in value.items():
            original_key = str(child_key)
            safe_key = _redact_text(original_key)
            if safe_key != original_key:
                safe_key = "[REDACTED_KEY]"
            redacted[safe_key] = redact_sensitive(child_value, key=original_key)
        return redacted
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact_sensitive(child) for child in value]
    if isinstance(value, str):
        return _redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return {"value_type": type(value).__name__}


def emit_alert(
    component: str, event: str, *, severity: str = "error",
    details: dict | None = None, timeout: float = 5.0,
) -> bool:
    """Emit a structured webhook alert when configured; always log locally."""
    safe_component = _redact_text(str(component))
    safe_event = _redact_text(str(event))
    safe_severity = _redact_text(str(severity))
    safe_details = redact_sensitive(details or {})
    payload = {
        "component": safe_component,
        "event": safe_event,
        "severity": safe_severity,
        "details": safe_details,
    }
    log = logger.error if severity in {"error", "critical"} else logger.warning
    log(
        "%s alert: %s · %s",
        safe_component,
        safe_event,
        json.dumps(safe_details, sort_keys=True),
    )
    url = (os.getenv("TRADINGAGENTS_ALERT_WEBHOOK_URL") or "").strip()
    if not url:
        return False
    request = Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "tradingagents/operations"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception as exc:  # noqa: BLE001 — alerts must not crash workers
        # urllib exceptions can include the complete webhook URL. Webhook URLs
        # commonly contain bearer material, so log only the exception class.
        logger.error("Could not deliver operations webhook (%s)", type(exc).__name__)
        return False
