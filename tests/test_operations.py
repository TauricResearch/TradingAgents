"""Production alerting must never copy webhook credentials into logs."""

import json
import logging

import pytest

from tradingagents import operations


@pytest.mark.unit
@pytest.mark.parametrize(
    ("severity", "expected_level"),
    [
        ("info", logging.INFO),
        ("warning", logging.WARNING),
        ("error", logging.ERROR),
        ("critical", logging.ERROR),
    ],
)
def test_alert_log_level_matches_payload_severity(
    monkeypatch, caplog, severity, expected_level,
):
    monkeypatch.delenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", raising=False)

    with caplog.at_level(logging.INFO):
        assert not operations.emit_alert("collector", "test", severity=severity)

    assert caplog.records[-1].levelno == expected_level


@pytest.mark.unit
def test_webhook_delivery_error_redacts_secret_url(monkeypatch, caplog):
    secret = "https://hooks.example.invalid/token/super-secret"
    monkeypatch.setenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", secret)

    def fail_with_url(*_args, **_kwargs):
        raise RuntimeError(f"failed to reach {secret}")

    monkeypatch.setattr(operations, "urlopen", fail_with_url)
    with caplog.at_level(logging.ERROR):
        assert not operations.emit_alert("test", "delivery")

    assert "RuntimeError" in caplog.text
    assert "super-secret" not in caplog.text
    assert secret not in caplog.text


@pytest.mark.unit
def test_webhook_payload_and_log_recursively_redact_credentials(monkeypatch, caplog):
    webhook = "https://hooks.example.invalid/token/webhook-secret"
    database = "postgresql://runtime:database-secret@db.example/research"
    bearer = "Bearer bearer-secret-value"
    api_key = "sk-example-secret-key-123456789"
    captured = {}

    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def deliver(request, timeout):
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", webhook)
    monkeypatch.setattr(operations, "urlopen", deliver)
    details = {
        "database_url": database,
        "nested": {
            "webhook_url": webhook,
            "authorization": bearer,
            "message": f"request to {webhook} used {bearer} and {api_key}",
        },
        "exception": RuntimeError(f"failed to reach {database}"),
        webhook: "secret key must not survive either",
        "artifact_id": "artifact_opaque",
        "count": 3,
    }
    with caplog.at_level(logging.ERROR):
        assert operations.emit_alert("paper-worker", "test", details=details, timeout=2.5)

    encoded = json.dumps(captured["payload"], sort_keys=True)
    assert captured["timeout"] == 2.5
    assert database not in encoded
    assert webhook not in encoded
    assert "bearer-secret-value" not in encoded
    assert api_key not in encoded
    assert database not in caplog.text
    assert webhook not in caplog.text
    assert "bearer-secret-value" not in caplog.text
    assert api_key not in caplog.text
    assert captured["payload"]["details"]["artifact_id"] == "artifact_opaque"
    assert captured["payload"]["details"]["count"] == 3
    assert captured["payload"]["details"]["database_url"] == "[REDACTED]"
    assert "[REDACTED_KEY]" in captured["payload"]["details"]


@pytest.mark.unit
def test_redact_sensitive_converts_unknown_objects_without_calling_string():
    class Dangerous:
        def __str__(self):
            raise AssertionError("must not stringify arbitrary alert detail objects")

    assert operations.redact_sensitive({"value": Dangerous()}) == {
        "value": {"value_type": "Dangerous"}
    }
