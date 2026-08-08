"""Small, fail-safe notification controls for the production collector."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from tradingagents.logging_utils import safe_exception_type

logger = logging.getLogger(__name__)

_SENSITIVE_KEY_PARTS = (
    "access_key",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "database_url",
    "dsn",
    "error",
    "exception",
    "password",
    "private_key",
    "secret",
    "token",
    "traceback",
    "url",
)
_URI = re.compile(r"\b[a-z][a-z0-9+.-]{0,31}://\S+", re.IGNORECASE)
_BEARER = re.compile(r"\bBearer\s+\S+", re.IGNORECASE)
_API_KEY = re.compile(r"\b(?:sk|xox[baprs]|gh[pousr])-[A-Za-z0-9_-]{12,}\b")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_DEDUPE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,127}")
_MAX_RESPONSE_BYTES = 4096

_ALERT_SPECS = {
    "delivery_test": ("test", "info"),
    "query_slot_coverage_incomplete": ("incident", "warning"),
    "query_slot_coverage_recovered": ("recovery", "info"),
    "runtime_unhealthy": ("incident", "critical"),
    "runtime_recovered": ("recovery", "info"),
}
_ALERT_CONTRACT_ID = (
    "alerts_"
    + hashlib.sha256(
        json.dumps(_ALERT_SPECS, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24]
)


def _redact_text(value: str) -> str:
    """Remove common credential-bearing strings without classifying secrets."""
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _API_KEY.sub("[REDACTED_KEY]", value)
    return _URI.sub("[REDACTED_URL]", value)


def redact_sensitive(value: Any, *, key: str | None = None) -> Any:
    """Return a JSON-safe copy with URLs, credentials, and exception text removed."""
    normalized_key = (key or "").strip().lower()
    if normalized_key and any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, BaseException):
        return {"exception_type": safe_exception_type(value)}
    if isinstance(value, Mapping):
        redacted = {}
        for child_key, child_value in value.items():
            if type(child_key) is not str:
                redacted["[REDACTED_KEY]"] = redact_sensitive(child_value)
                continue
            original_key = child_key
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


def _safe_identifier(value: object, fallback: str) -> str:
    if type(value) is not str:
        return fallback
    candidate = value.strip().lower()
    return candidate if _IDENTIFIER.fullmatch(candidate) else fallback


def _webhook_url() -> str:
    url = (os.getenv("TRADINGAGENTS_ALERT_WEBHOOK_URL") or "").strip()
    if not url:
        return ""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("alert webhook must be an HTTPS URL without credentials or fragments")
    return url


def _notification_payload(
    component: object,
    event: object,
    severity: object,
    dedupe_key: object | None,
) -> dict | None:
    if type(component) is not str or component != "collector":
        return None
    safe_component = "collector"
    safe_event = _safe_identifier(event, "unknown")
    safe_severity = _safe_identifier(severity, "error")
    if safe_severity not in {"info", "warning", "error", "critical"}:
        safe_severity = "error"
    spec = _ALERT_SPECS.get(safe_event)
    if spec is None or safe_severity != spec[1]:
        return None
    kind, safe_severity = spec
    if safe_event == "delivery_test":
        if dedupe_key is not None:
            return None
        occurrence = secrets.token_hex(16)
    else:
        if type(dedupe_key) is not str or _DEDUPE_KEY.fullmatch(dedupe_key) is None:
            return None
        occurrence = dedupe_key
    material = (
        f"alerts-v1\0{safe_component}\0{safe_event}\0{safe_severity}\0{occurrence}"
    ).encode()
    return {
        "schema_version": 1,
        "contract_id": _ALERT_CONTRACT_ID,
        "kind": kind,
        "idempotency_key": hashlib.sha256(material).hexdigest()[:32],
        "component": safe_component,
        "event": safe_event,
        "severity": safe_severity,
    }


def _matches_acknowledgement(value: Any, expected: dict) -> bool:
    """Require the receiver's complete, typed acknowledgement contract."""
    return (
        type(value) is dict
        and value.keys() == expected.keys()
        and all(
            type(value[key]) is type(expected_value) and value[key] == expected_value
            for key, expected_value in expected.items()
        )
    )


def _delivery_failed(reason: str) -> bool:
    """Record one fixed-vocabulary delivery failure without response content."""
    logger.warning("Operations webhook was not acknowledged (%s)", reason)
    return False


def _post(payload: dict, *, timeout: float, expected_ack: dict) -> bool:
    """Post one bounded JSON message and require a matching receiver acknowledgement."""
    try:
        url = _webhook_url()
    except ValueError:
        return _delivery_failed("invalid_configuration")
    try:
        if not url:
            return _delivery_failed("not_configured")
        request = Request(
            url,
            data=json.dumps(payload, separators=(",", ":")).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "tradingagents/operations",
            },
        )
        with urlopen(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                return _delivery_failed("http_status")
            body = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(body) > _MAX_RESPONSE_BYTES:
            return _delivery_failed("response_too_large")
        try:
            acknowledgement = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _delivery_failed("invalid_ack")
        if not _matches_acknowledgement(acknowledgement, expected_ack):
            return _delivery_failed("invalid_ack")
        return True
    except HTTPError:
        return _delivery_failed("http_status")
    except Exception:  # noqa: BLE001 - URLs and transport text can contain secrets
        return _delivery_failed("request_failed")


def emit_alert(
    component: str,
    event: str,
    *,
    severity: str = "error",
    details: dict | None = None,
    timeout: float = 5.0,
    dedupe_key: object | None = None,
) -> bool:
    """Log technical context locally and send only compact, fixed user-facing copy."""
    try:
        payload = _notification_payload(component, event, severity, dedupe_key)
        if payload is None:
            logger.error("Rejected unknown operations alert event")
            return False
        try:
            safe_details = redact_sensitive(details or {})
        except Exception:  # noqa: BLE001 - diagnostics cannot block an alert
            safe_details = {"diagnostic_state": "unavailable"}
        log = {
            "info": logger.info,
            "warning": logger.warning,
            "error": logger.error,
            "critical": logger.error,
        }[payload["severity"]]
        log(
            "%s alert: %s · %s",
            payload["component"],
            payload["event"],
            json.dumps(safe_details, sort_keys=True),
        )
        return _post(
            payload,
            timeout=timeout,
            expected_ack={
                "schema_version": 1,
                "contract_id": _ALERT_CONTRACT_ID,
                "kind": payload["kind"],
                "idempotency_key": payload["idempotency_key"],
                "accepted": True,
            },
        )
    except Exception as exc:  # noqa: BLE001 - notifications must never crash workers
        logger.error("Could not prepare operations webhook (%s)", safe_exception_type(exc))
        return False


def probe_alert_webhook(*, timeout: float = 5.0) -> bool:
    """Verify the receiver contract without creating a human notification."""
    nonce = secrets.token_hex(16)
    payload = {
        "schema_version": 1,
        "contract_id": _ALERT_CONTRACT_ID,
        "kind": "probe",
        "nonce": nonce,
    }
    return _post(
        payload,
        timeout=timeout,
        expected_ack={
            "schema_version": 1,
            "contract_id": _ALERT_CONTRACT_ID,
            "kind": "probe",
            "nonce": nonce,
            "accepted": True,
        },
    )
