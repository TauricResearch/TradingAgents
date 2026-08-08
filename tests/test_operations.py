"""Production alerting must never copy webhook credentials into logs."""

import json
import logging
from urllib.error import HTTPError

import pytest

from tradingagents import operations


class _Response:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit: int):
        return self.body[:limit]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event", "severity", "expected_level"),
    [
        ("delivery_test", "info", logging.INFO),
        ("query_slot_coverage_incomplete", "warning", logging.WARNING),
        ("runtime_unhealthy", "critical", logging.ERROR),
    ],
)
def test_alert_log_level_matches_payload_severity(
    monkeypatch,
    caplog,
    event,
    severity,
    expected_level,
):
    monkeypatch.delenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", raising=False)
    dedupe_key = None if event == "delivery_test" else "test-incident"

    with caplog.at_level(logging.INFO):
        assert not operations.emit_alert(
            "collector", event, severity=severity, dedupe_key=dedupe_key
        )

    event_record = next(
        record for record in caplog.records
        if record.getMessage().startswith("collector alert:")
    )
    assert event_record.levelno == expected_level
    assert "Operations webhook was not acknowledged (not_configured)" in caplog.text


@pytest.mark.unit
def test_webhook_delivery_error_redacts_secret_url(monkeypatch, caplog):
    secret = "https://hooks.example.invalid/token/super-secret"
    monkeypatch.setenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", secret)

    def fail_with_url(*_args, **_kwargs):
        raise RuntimeError(f"failed to reach {secret}")

    monkeypatch.setattr(operations, "urlopen", fail_with_url)
    with caplog.at_level(logging.INFO):
        assert not operations.emit_alert("collector", "delivery_test", severity="info")

    assert "Operations webhook was not acknowledged (request_failed)" in caplog.text
    assert "RuntimeError" not in caplog.text
    assert "super-secret" not in caplog.text
    assert secret not in caplog.text


@pytest.mark.unit
@pytest.mark.parametrize(
    "url",
    [
        "http://receiver.example.invalid/exec",
        "https://user:password@receiver.example.invalid/exec",
        "https://receiver.example.invalid/exec#secret-fragment",
    ],
)
def test_webhook_rejects_unsafe_urls_without_connecting(monkeypatch, caplog, url):
    monkeypatch.setenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", url)
    monkeypatch.setattr(
        operations,
        "urlopen",
        lambda *_args, **_kwargs: pytest.fail("unsafe webhook must not be opened"),
    )

    with caplog.at_level(logging.INFO):
        assert not operations.emit_alert("collector", "delivery_test", severity="info")

    assert "Operations webhook was not acknowledged (invalid_configuration)" in caplog.text


@pytest.mark.unit
def test_http_error_has_a_fixed_status_reason_without_response_details(monkeypatch, caplog):
    secret = "must-not-be-logged"
    url = f"https://receiver.example.invalid/{secret}"
    monkeypatch.setenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", url)

    def reject(*_args, **_kwargs):
        raise HTTPError(url, 503, secret, None, None)

    monkeypatch.setattr(operations, "urlopen", reject)
    with caplog.at_level(logging.INFO):
        assert not operations.emit_alert("collector", "delivery_test", severity="info")

    assert "Operations webhook was not acknowledged (http_status)" in caplog.text
    assert secret not in caplog.text


@pytest.mark.unit
def test_webhook_payload_and_log_recursively_redact_credentials(monkeypatch, caplog):
    webhook = "https://hooks.example.invalid/token/webhook-secret"
    database = "postgresql://runtime:database-secret@db.example/research"
    bearer = "Bearer bearer-secret-value"
    api_key = "sk-example-secret-key-123456789"
    captured = {}

    def deliver(request, timeout):
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        payload = captured["payload"]
        return _Response(
            200,
            json.dumps(
                {
                    "schema_version": 1,
                    "contract_id": payload["contract_id"],
                    "kind": payload["kind"],
                    "idempotency_key": payload["idempotency_key"],
                    "accepted": True,
                }
            ).encode(),
        )

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
    with caplog.at_level(logging.INFO):
        assert operations.emit_alert(
            "collector",
            "delivery_test",
            severity="info",
            details=details,
            timeout=2.5,
        )

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
    assert captured["payload"] == {
        "schema_version": 1,
        "contract_id": operations._ALERT_CONTRACT_ID,
        "kind": "test",
        "idempotency_key": captured["payload"]["idempotency_key"],
        "component": "collector",
        "event": "delivery_test",
        "severity": "info",
    }
    assert len(captured["payload"]["idempotency_key"]) == 32
    assert "artifact_opaque" in caplog.text
    assert "count" in caplog.text


@pytest.mark.unit
def test_redact_sensitive_converts_unknown_objects_without_calling_string():
    class Dangerous:
        def __str__(self):
            raise AssertionError("must not stringify arbitrary alert detail objects")

    assert operations.redact_sensitive({"value": Dangerous(), Dangerous(): "value"}) == {
        "value": {"value_type": "Dangerous"},
        "[REDACTED_KEY]": "value",
    }


@pytest.mark.unit
def test_malformed_diagnostics_cannot_block_a_fixed_alert(monkeypatch, caplog):
    captured = {}

    def deliver(request, timeout):
        assert timeout == 5.0
        payload = json.loads(request.data)
        captured.update(payload)
        return _Response(
            200,
            json.dumps(
                {
                    "schema_version": 1,
                    "contract_id": payload["contract_id"],
                    "kind": payload["kind"],
                    "idempotency_key": payload["idempotency_key"],
                    "accepted": True,
                }
            ).encode(),
        )

    recursive = {}
    recursive["nested"] = recursive
    monkeypatch.setenv(
        "TRADINGAGENTS_ALERT_WEBHOOK_URL",
        "https://receiver.example.invalid/exec",
    )
    monkeypatch.setattr(operations, "urlopen", deliver)

    with caplog.at_level(logging.INFO):
        assert operations.emit_alert(
            "collector", "delivery_test", severity="info", details=recursive
        )

    assert captured["event"] == "delivery_test"
    assert '"diagnostic_state": "unavailable"' in caplog.text


@pytest.mark.unit
def test_redact_sensitive_covers_opaque_key_names_and_generic_uris():
    details = {
        "api_key": "opaque-api-value",
        "ApiKey": "opaque-apikey-value",
        "access_key_id": "opaque-access-value",
        "private_key_pem": "opaque-private-value",
        "message": "failed to open custom+ssh://user:secret@example.invalid/path",
    }

    encoded = json.dumps(operations.redact_sensitive(details))

    assert "opaque" not in encoded
    assert "custom+ssh://" not in encoded
    assert "[REDACTED_URL]" in encoded


@pytest.mark.unit
def test_non_collector_component_is_rejected_without_stringifying_it(monkeypatch, caplog):
    class Dangerous:
        def __str__(self):
            raise RuntimeError("must stay contained")

    with caplog.at_level(logging.ERROR):
        assert not operations.emit_alert(Dangerous(), "delivery_test")

    assert "Rejected unknown operations alert event" in caplog.text
    assert "must stay contained" not in caplog.text


@pytest.mark.unit
@pytest.mark.parametrize("component", ["Collector", " collector", "paper-worker", None])
def test_notification_payload_accepts_only_the_exact_collector_component(component):
    assert operations._notification_payload(component, "delivery_test", "info", None) is None


@pytest.mark.unit
def test_probe_requires_nonce_ack_and_has_no_notification_fields(monkeypatch):
    captured = {}

    def deliver(request, timeout):
        assert timeout == 5.0
        captured["payload"] = json.loads(request.data)
        payload = captured["payload"]
        return _Response(
            200,
            json.dumps(
                {
                    "schema_version": 1,
                    "contract_id": payload["contract_id"],
                    "kind": "probe",
                    "nonce": payload["nonce"],
                    "accepted": True,
                }
            ).encode(),
        )

    monkeypatch.setenv(
        "TRADINGAGENTS_ALERT_WEBHOOK_URL",
        "https://script.google.com/macros/s/deployment/exec",
    )
    monkeypatch.setattr(operations, "urlopen", deliver)

    assert operations.probe_alert_webhook()
    assert set(captured["payload"]) == {
        "schema_version",
        "contract_id",
        "kind",
        "nonce",
    }
    assert captured["payload"]["kind"] == "probe"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("body", "status"),
    [
        (b"not-json", 200),
        (json.dumps({"schema_version": 1}).encode(), 200),
        (json.dumps({"schema_version": 2, "accepted": True}).encode(), 200),
        (json.dumps({"schema_version": 1, "accepted": False}).encode(), 200),
        (json.dumps({"schema_version": 1, "accepted": True, "extra": 1}).encode(), 200),
        (json.dumps({"schema_version": True, "accepted": True}).encode(), 200),
        (json.dumps({"schema_version": 1, "accepted": 1}).encode(), 200),
        (json.dumps("x" * operations._MAX_RESPONSE_BYTES).encode(), 200),
        (b"", 204),
    ],
)
def test_post_rejects_malformed_or_inexact_acknowledgements(
    monkeypatch,
    body,
    status,
):
    monkeypatch.setenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", "https://receiver.example.invalid/exec")
    monkeypatch.setattr(operations, "urlopen", lambda *_args, **_kwargs: _Response(status, body))

    assert not operations._post(
        {"probe": True},
        timeout=1,
        expected_ack={"schema_version": 1, "accepted": True},
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "expected"),
    [(199, False), (200, True), (299, True), (300, False)],
)
def test_post_accepts_only_success_status_with_exact_ack(monkeypatch, status, expected):
    acknowledgement = {"schema_version": 1, "accepted": True}
    monkeypatch.setenv("TRADINGAGENTS_ALERT_WEBHOOK_URL", "https://receiver.example.invalid/exec")
    monkeypatch.setattr(
        operations,
        "urlopen",
        lambda *_args, **_kwargs: _Response(status, json.dumps(acknowledgement).encode()),
    )

    assert operations._post({"probe": True}, timeout=1, expected_ack=acknowledgement) is expected


@pytest.mark.unit
def test_notification_ids_dedupe_retries_but_not_new_incidents_or_tests():
    first = operations._notification_payload(
        "collector", "runtime_unhealthy", "critical", "incident-a"
    )
    retry = operations._notification_payload(
        "collector", "runtime_unhealthy", "critical", "incident-a"
    )
    recurrence = operations._notification_payload(
        "collector", "runtime_unhealthy", "critical", "incident-b"
    )
    test_one = operations._notification_payload("collector", "delivery_test", "info", None)
    test_two = operations._notification_payload("collector", "delivery_test", "info", None)

    assert first is not None and retry is not None and recurrence is not None
    assert test_one is not None and test_two is not None
    assert first["idempotency_key"] == retry["idempotency_key"]
    assert first["idempotency_key"] != recurrence["idempotency_key"]
    assert test_one["idempotency_key"] != test_two["idempotency_key"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "dedupe_key",
    [None, "", " leading", "contains spaces", "x" * 129, 1, object()],
)
def test_incident_payload_requires_a_bounded_canonical_dedupe_key(dedupe_key):
    assert operations._notification_payload(
        "collector", "runtime_unhealthy", "critical", dedupe_key
    ) is None


@pytest.mark.unit
def test_delivery_test_rejects_a_misleading_caller_dedupe_key():
    assert operations._notification_payload(
        "collector", "delivery_test", "info", "unused"
    ) is None


@pytest.mark.unit
def test_alert_contract_contains_only_actionable_collector_events():
    assert operations._ALERT_SPECS == {
        "delivery_test": ("test", "info"),
        "query_slot_coverage_incomplete": ("incident", "warning"),
        "query_slot_coverage_recovered": ("recovery", "info"),
        "runtime_unhealthy": ("incident", "critical"),
        "runtime_recovered": ("recovery", "info"),
    }
    assert operations._notification_payload("paper-worker", "delivery_test", "info", None) is None
