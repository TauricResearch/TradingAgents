"""Current-process collector health must fail closed and expose no evidence."""

import hashlib
import json
import signal
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from tradingagents import collector_health, poller
from tradingagents.collector_health import (
    _READINESS_RESPONSE_MAX_BYTES,
    CollectorHealthServer,
    CollectorHealthState,
    probe_collector_readiness,
    readiness_probe_main,
)

STATIC_SLOTS = [
    {"provider": "globalnews", "query_key": f"theme-{index}:query"} for index in range(10)
]
STATIC_SLOT_IDS = {
    hashlib.sha256(f"{slot['provider']}\0{slot['query_key']}".encode()).hexdigest()[:16]
    for slot in STATIC_SLOTS
}
DEPLOYMENT_NONCE = "1" * 32


def _complete_coverage(*, dynamic: bool = False):
    slots = [{**slot, "healthy": True, "reason": None} for slot in STATIC_SLOTS]
    if dynamic:
        slots.append(
            {
                "provider": "x",
                "query_key": "discovered topic",
                "healthy": True,
                "reason": None,
            }
        )
    return {
        "complete": True,
        "missing_query_slots": [],
        "missing_periodic_requirements": [],
        "query_slots": slots,
    }


def _incomplete_coverage():
    slots = _complete_coverage()["query_slots"]
    slots[0] = {**slots[0], "healthy": False, "reason": "failed"}
    return {
        "complete": False,
        "missing_query_slots": [{**STATIC_SLOTS[0], "reason": "failed"}],
        "missing_periodic_requirements": [],
        "query_slots": slots,
    }


@pytest.mark.unit
def test_health_state_requires_current_process_cycle_and_fails_closed():
    revision = "a" * 40
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
        build_revision=revision,
        machine_id="machine-123",
        deployment_nonce=DEPLOYMENT_NONCE,
    )

    status, starting = state.snapshot(monotonic_now=100.0)
    assert status == 503
    assert starting == {
        "schema_version": 1,
        "status": "unhealthy",
        "reason": "starting",
        "expected_query_slot_count": 10,
        "missing_query_slot_count": 10,
        "missing_periodic_requirement_count": 0,
        "missing_requirement_count": 10,
        "last_cycle_age_seconds": None,
        "build_revision": revision,
        "machine_id": "machine-123",
        "deployment_nonce": DEPLOYMENT_NONCE,
    }

    # Malformed orchestration is a runtime invariant failure, never a degraded
    # cycle that can overwrite this process's health state.
    malformed_complete = _complete_coverage()
    malformed_complete["complete"] = "true"
    with pytest.raises(ValueError, match="completeness"):
        state.mark_cycle(
            malformed_complete,
            completed_utc=110.0,
            completed_monotonic=110.0,
        )
    status, malformed = state.snapshot(monotonic_now=120.0)
    assert status == 503
    assert malformed["reason"] == "starting"

    # Dynamic X slots may extend, but never replace, that static manifest.
    state.mark_cycle(
        _complete_coverage(dynamic=True),
        completed_utc=110.0,
        completed_monotonic=110.0,
    )
    status, healthy = state.snapshot(monotonic_now=120.0)
    assert status == 200
    assert healthy["reason"] == "healthy"
    assert healthy["expected_query_slot_count"] == len(STATIC_SLOTS) + 1
    assert healthy["last_cycle_age_seconds"] == 10.0

    status, stale = state.snapshot(monotonic_now=171.0)
    assert status == 503
    assert stale["reason"] == "stale"

    state.mark_failure("ProgrammingError")
    status, failed = state.snapshot(monotonic_now=172.0)
    assert status == 503
    assert failed["reason"] == "cycle_failed"
    assert failed["failure_type"] == "ProgrammingError"


@pytest.mark.unit
@pytest.mark.parametrize("max_age", [True, "60", 0, float("inf"), float("nan"), 10**1000])
def test_health_state_rejects_invalid_max_age_types(max_age):
    with pytest.raises(ValueError, match="max age"):
        CollectorHealthState(
            max_age_seconds=max_age,
            expected_query_slot_ids=STATIC_SLOT_IDS,
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("build_revision", 1, "build revision"),
        ("machine_id", 1, "machine ID"),
        ("deployment_nonce", 1, "deployment nonce"),
    ],
)
def test_health_state_rejects_non_string_process_identity(keyword, value, message):
    with pytest.raises(ValueError, match=message):
        CollectorHealthState(
            max_age_seconds=60.0,
            expected_query_slot_ids=STATIC_SLOT_IDS,
            **{keyword: value},
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "identity",
    [
        {"machine_id": "machine-123"},
        {"machine_id": "machine-123", "build_revision": "a" * 40},
        {"machine_id": "machine-123", "deployment_nonce": DEPLOYMENT_NONCE},
    ],
)
def test_health_state_requires_a_complete_fly_process_identity(identity):
    with pytest.raises(ValueError, match="Fly process identity must be complete"):
        CollectorHealthState(
            max_age_seconds=60.0,
            expected_query_slot_ids=STATIC_SLOT_IDS,
            **identity,
        )


@pytest.mark.unit
@pytest.mark.parametrize("completed_utc", [True, "100", float("inf")])
def test_health_state_rejects_invalid_completion_time_types(completed_utc):
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    with pytest.raises(ValueError, match="completion time"):
        state.mark_cycle(_complete_coverage(), completed_utc=completed_utc)


@pytest.mark.unit
@pytest.mark.parametrize("completed_monotonic", [True, "100", float("nan")])
def test_health_state_rejects_invalid_monotonic_time_types(completed_monotonic):
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    with pytest.raises(ValueError, match="monotonic time"):
        state.mark_cycle(
            _complete_coverage(),
            completed_utc=100.0,
            completed_monotonic=completed_monotonic,
        )


@pytest.mark.unit
@pytest.mark.parametrize("monotonic_now", [True, "100", float("-inf")])
def test_health_state_rejects_invalid_observation_time_types(monotonic_now):
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    with pytest.raises(ValueError, match="observation"):
        state.snapshot(monotonic_now=monotonic_now)


@pytest.mark.unit
@pytest.mark.parametrize("port", [True, "5500", -1, 65536])
def test_health_server_rejects_invalid_port_types(port):
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    with pytest.raises(ValueError, match="port"):
        CollectorHealthServer(state, host="127.0.0.1", port=port)


@pytest.mark.unit
def test_health_failure_type_is_sanitized_before_string_operations():
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    state.mark_failure(None)

    status, payload = state.readiness_snapshot(monotonic_now=100.0)

    assert status == 503
    assert payload["reason"] == "cycle_failed"
    assert payload["failure_type"] == "Exception"


@pytest.mark.unit
def test_readiness_recovers_on_an_incomplete_terminal_cycle():
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )

    status, starting = state.readiness_snapshot(monotonic_now=100.0)
    assert status == 503
    assert starting["reason"] == "starting"

    state.mark_failure("OperationalError")
    status, failed = state.readiness_snapshot(monotonic_now=101.0)
    assert status == 503
    assert failed["reason"] == "cycle_failed"

    state.mark_cycle(
        _incomplete_coverage(),
        completed_utc=102.0,
        completed_monotonic=102.0,
    )
    health_status, health = state.snapshot(monotonic_now=103.0)
    ready_status, ready = state.readiness_snapshot(monotonic_now=103.0)

    assert health_status == 503
    assert health["reason"] == "coverage_incomplete"
    assert ready_status == 200
    assert ready["reason"] == "ready"
    assert ready["missing_query_slot_count"] == 1
    assert "failure_type" not in ready

    status, stale = state.readiness_snapshot(monotonic_now=163.0)
    assert status == 503
    assert stale["reason"] == "stale"


@pytest.mark.unit
def test_health_http_endpoint_is_private_projection_only():
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    server = CollectorHealthServer(state, host="127.0.0.1", port=0)
    try:
        base_url = f"http://127.0.0.1:{server.port}"
        health_url = f"{base_url}/healthz"
        ready_url = f"{base_url}/readyz"
        with pytest.raises(HTTPError) as exc_info:
            urlopen(ready_url, timeout=2.0)  # noqa: S310 - loopback test server
        with exc_info.value as response:
            assert response.code == 503
            starting = json.load(response)
        assert starting["reason"] == "starting"

        state.mark_cycle(
            _incomplete_coverage(),
            completed_utc=10**10,
        )
        with pytest.raises(HTTPError) as incomplete:
            urlopen(health_url, timeout=2.0)  # noqa: S310 - loopback test server
        with incomplete.value as response:
            assert response.code == 503
            assert json.load(response)["reason"] == "coverage_incomplete"

        with urlopen(ready_url, timeout=2.0) as response:  # noqa: S310
            assert response.status == 200
            payload = json.load(response)
        assert payload["status"] == "ok"
        assert payload["reason"] == "ready"
        assert "query_key" not in payload
        assert "url" not in payload

        state.mark_cycle(_complete_coverage(), completed_utc=10**10)
        with urlopen(health_url, timeout=2.0) as response:  # noqa: S310
            assert response.status == 200
            assert json.load(response)["reason"] == "healthy"

        with pytest.raises(HTTPError) as missing:
            urlopen(  # noqa: S310 - loopback test server
                f"{base_url}/not-health", timeout=2.0
            )
        with missing.value as response:
            assert response.code == 404
    finally:
        server.close()


@pytest.mark.unit
@pytest.mark.parametrize("cycle_fails", [False, True])
def test_daemon_health_tracks_this_process_cycle(monkeypatch, cycle_fails):
    handlers = {}
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    monkeypatch.setattr(
        poller.signal,
        "signal",
        lambda signum, handler: handlers.__setitem__(signum, handler),
    )
    monkeypatch.setattr(poller.time, "time", lambda: 100.0)
    monkeypatch.setattr(collector_health.time, "monotonic", lambda: 200.0)

    def one_cycle(*_args, **_kwargs):
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        if cycle_fails:
            raise RuntimeError("database detail must not enter health")
        return _complete_coverage()

    monkeypatch.setattr(poller, "run_cycle", one_cycle)
    if cycle_fails:
        with pytest.raises(RuntimeError, match=r"collector cycle failed \(RuntimeError\)"):
            poller.poll_forever(object(), [], [], 3600, {}, health_state=state)
    else:
        poller.poll_forever(object(), [], [], 3600, {}, health_state=state)

    status, payload = state.snapshot(monotonic_now=200.0)
    if cycle_fails:
        assert status == 503
        assert payload["reason"] == "cycle_failed"
        assert payload["failure_type"] == "RuntimeError"
        assert "database detail" not in json.dumps(payload)
    else:
        assert status == 200
        assert payload["reason"] == "healthy"


@pytest.mark.unit
def test_daemon_invariant_failure_terminates_without_sleeping(monkeypatch):
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    monkeypatch.setattr(poller.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(
        poller,
        "run_cycle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("private database invariant detail")
        ),
    )
    sleeps = []
    monkeypatch.setattr(poller, "_sleep", lambda *args: sleeps.append(args))

    with pytest.raises(RuntimeError, match=r"collector cycle failed \(ValueError\)"):
        poller.poll_forever(object(), [], [], 3600, {}, health_state=state)

    assert sleeps == []
    status, payload = state.snapshot(monotonic_now=100.0)
    assert status == 503
    assert payload["failure_type"] == "ValueError"
    assert "private database" not in json.dumps(payload)


@pytest.mark.unit
def test_health_freshness_uses_monotonic_time_when_wall_clock_moves_backward(
    monkeypatch,
):
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    monkeypatch.setattr(collector_health.time, "time", lambda: 1_000.0)
    state.mark_cycle(
        _complete_coverage(),
        completed_utc=1_000.0,
        completed_monotonic=50.0,
    )

    # NTP correction moves UTC backward while process time advances normally.
    monkeypatch.setattr(collector_health.time, "time", lambda: 100.0)
    status, payload = state.snapshot(monotonic_now=55.0)

    assert status == 200
    assert payload["last_cycle_age_seconds"] == 5.0


@pytest.mark.unit
def test_health_reports_missing_periodic_requirements_separately():
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    coverage = {
        **_complete_coverage(),
        "complete": False,
        "missing_periodic_requirements": ["x_daily"],
    }
    state.mark_cycle(
        coverage,
        completed_utc=100.0,
        completed_monotonic=100.0,
    )

    status, payload = state.snapshot(monotonic_now=101.0)

    assert status == 503
    assert payload["reason"] == "coverage_incomplete"
    assert payload["missing_query_slot_count"] == 0
    assert payload["missing_periodic_requirement_count"] == 1
    assert payload["missing_requirement_count"] == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "missing_field",
    ["query_slots", "missing_query_slots", "missing_periodic_requirements"],
)
def test_health_rejects_an_omitted_required_coverage_list(missing_field):
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    coverage = _complete_coverage()
    del coverage[missing_field]

    with pytest.raises(ValueError, match=missing_field):
        state.mark_cycle(
            coverage,
            completed_utc=100.0,
            completed_monotonic=100.0,
        )

    status, payload = state.readiness_snapshot(monotonic_now=101.0)
    assert status == 503
    assert payload["reason"] == "starting"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("query_slots", "not-a-list"),
        ("query_slots", [{"provider": "globalnews"}]),
        ("missing_query_slots", ["not-a-slot"]),
        ("missing_periodic_requirements", ["x_daily", "x_daily"]),
        ("missing_periodic_requirements", [{"period": "daily"}]),
    ],
)
def test_health_rejects_malformed_coverage_list_entries(field, value):
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    coverage = _complete_coverage()
    coverage[field] = value

    with pytest.raises(ValueError, match=field):
        state.mark_cycle(
            coverage,
            completed_utc=100.0,
            completed_monotonic=100.0,
        )


@pytest.mark.unit
@pytest.mark.parametrize("field", ["query_slots", "missing_query_slots"])
def test_health_rejects_duplicate_query_slots(field):
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    coverage = _incomplete_coverage()
    coverage[field] = [*coverage[field], coverage[field][0]]

    with pytest.raises(ValueError, match="unique"):
        state.mark_cycle(
            coverage,
            completed_utc=100.0,
            completed_monotonic=100.0,
        )


@pytest.mark.unit
def test_health_rejects_a_missing_slot_outside_the_observed_manifest():
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    coverage = _incomplete_coverage()
    coverage["missing_query_slots"] = [
        {"provider": "globalnews", "query_key": "not-observed", "reason": "failed"}
    ]

    with pytest.raises(ValueError, match="do not match"):
        state.mark_cycle(
            coverage,
            completed_utc=100.0,
            completed_monotonic=100.0,
        )


@pytest.mark.unit
def test_health_rejects_an_absent_required_static_slot():
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    coverage = _complete_coverage()
    coverage["query_slots"].pop()

    with pytest.raises(ValueError, match="omitted required"):
        state.mark_cycle(
            coverage,
            completed_utc=100.0,
            completed_monotonic=100.0,
        )


@pytest.mark.unit
def test_health_rejects_an_unreported_unhealthy_query_slot():
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    coverage = _complete_coverage()
    coverage["query_slots"][0] = {
        **coverage["query_slots"][0],
        "healthy": False,
        "reason": "failed",
    }

    with pytest.raises(ValueError, match="do not match"):
        state.mark_cycle(
            coverage,
            completed_utc=100.0,
            completed_monotonic=100.0,
        )


@pytest.mark.unit
def test_health_rejects_complete_coverage_with_a_missing_requirement():
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    coverage = _incomplete_coverage()
    coverage["complete"] = True

    with pytest.raises(ValueError, match="completeness"):
        state.mark_cycle(
            coverage,
            completed_utc=100.0,
            completed_monotonic=100.0,
        )


@pytest.mark.unit
def test_health_rejects_incomplete_coverage_without_a_missing_requirement():
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    coverage = {**_complete_coverage(), "complete": False}

    with pytest.raises(ValueError, match="completeness"):
        state.mark_cycle(
            coverage,
            completed_utc=100.0,
            completed_monotonic=100.0,
        )


@pytest.mark.unit
def test_health_fails_stale_without_serializing_an_overflowed_age():
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    state.mark_cycle(
        _complete_coverage(),
        completed_utc=100.0,
        completed_monotonic=-1e308,
    )

    status, payload = state.readiness_snapshot(monotonic_now=1e308)

    assert status == 503
    assert payload["reason"] == "stale"
    assert payload["last_cycle_age_seconds"] is None


@pytest.mark.unit
def test_malformed_cycle_projection_becomes_a_runtime_failure(monkeypatch):
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    malformed = _complete_coverage()
    del malformed["missing_periodic_requirements"]
    monkeypatch.setattr(poller.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(poller, "run_cycle", lambda *_args, **_kwargs: malformed)

    with pytest.raises(RuntimeError, match=r"collector cycle failed \(ValueError\)"):
        poller.poll_forever(object(), [], [], 3600, {}, health_state=state)

    status, payload = state.readiness_snapshot(monotonic_now=100.0)
    assert status == 503
    assert payload["reason"] == "cycle_failed"
    assert payload["failure_type"] == "ValueError"


class _ReadinessState:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    def readiness_snapshot(self):
        return self.status, self.payload

    def snapshot(self):
        return self.status, self.payload


def _readiness_payload():
    return {
        "schema_version": 1,
        "status": "ok",
        "reason": "ready",
        "expected_query_slot_count": len(STATIC_SLOT_IDS),
        "missing_query_slot_count": 1,
        "missing_periodic_requirement_count": 1,
        "missing_requirement_count": 2,
        "last_cycle_age_seconds": 0.25,
        "build_revision": "a" * 40,
        "machine_id": "machine-123",
        "deployment_nonce": DEPLOYMENT_NONCE,
    }


@pytest.mark.unit
def test_local_readiness_probe_binds_the_exact_process_revision_and_machine(capsys):
    server = CollectorHealthServer(
        _ReadinessState(200, _readiness_payload()),
        host="127.0.0.1",
        port=0,
    )
    try:
        assert probe_collector_readiness(
            expected_build_revision="a" * 40,
            expected_machine_id="machine-123",
            expected_deployment_nonce=DEPLOYMENT_NONCE,
            port=server.port,
        )
        assert not probe_collector_readiness(
            expected_build_revision="b" * 40,
            expected_machine_id="machine-123",
            expected_deployment_nonce=DEPLOYMENT_NONCE,
            port=server.port,
        )
        assert not probe_collector_readiness(
            expected_build_revision="a" * 40,
            expected_machine_id="machine-456",
            expected_deployment_nonce=DEPLOYMENT_NONCE,
            port=server.port,
        )
        assert not probe_collector_readiness(
            expected_build_revision="a" * 40,
            expected_machine_id="machine-123",
            expected_deployment_nonce="2" * 32,
            port=server.port,
        )
        assert (
            readiness_probe_main(
                [
                    "--expected-build-revision",
                    "a" * 40,
                    "--expected-machine-id",
                    "machine-123",
                    "--expected-deployment-nonce",
                    DEPLOYMENT_NONCE,
                ],
                environ={"MEDIA_HEALTH_PORT": str(server.port)},
            )
            == 0
        )
    finally:
        server.close()
    assert capsys.readouterr() == ("", "")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("http_status", "field", "value"),
    [
        (503, "reason", "ready"),
        (200, "schema_version", True),
        (200, "status", "unhealthy"),
        (200, "reason", "healthy"),
        (200, "build_revision", "b" * 40),
        (200, "machine_id", "machine-456"),
        (200, "deployment_nonce", "2" * 32),
        (200, "expected_query_slot_count", 0),
        (200, "missing_requirement_count", 3),
        (200, "missing_query_slot_count", True),
        (200, "last_cycle_age_seconds", float("inf")),
        (200, "last_cycle_age_seconds", 10**1000),
    ],
)
def test_local_readiness_probe_rejects_wrong_status_identity_or_payload(http_status, field, value):
    payload = {**_readiness_payload(), field: value}
    server = CollectorHealthServer(_ReadinessState(http_status, payload), host="127.0.0.1", port=0)
    try:
        assert not probe_collector_readiness(
            expected_build_revision="a" * 40,
            expected_machine_id="machine-123",
            expected_deployment_nonce=DEPLOYMENT_NONCE,
            port=server.port,
        )
    finally:
        server.close()


@pytest.mark.unit
def test_local_readiness_probe_rejects_an_oversized_response_without_output(capsys):
    payload = {
        **_readiness_payload(),
        "padding": "x" * _READINESS_RESPONSE_MAX_BYTES,
    }
    server = CollectorHealthServer(_ReadinessState(200, payload), host="127.0.0.1", port=0)
    try:
        assert not probe_collector_readiness(
            expected_build_revision="a" * 40,
            expected_machine_id="machine-123",
            expected_deployment_nonce=DEPLOYMENT_NONCE,
            port=server.port,
        )
    finally:
        server.close()
    assert capsys.readouterr() == ("", "")


@pytest.mark.unit
@pytest.mark.parametrize("schema_change", ["extra", "missing"])
def test_local_readiness_probe_requires_the_exact_payload_schema(schema_change):
    payload = _readiness_payload()
    if schema_change == "extra":
        payload["unexpected"] = "field"
    else:
        del payload["last_cycle_age_seconds"]
    server = CollectorHealthServer(_ReadinessState(200, payload), host="127.0.0.1", port=0)
    try:
        assert not probe_collector_readiness(
            expected_build_revision="a" * 40,
            expected_machine_id="machine-123",
            expected_deployment_nonce=DEPLOYMENT_NONCE,
            port=server.port,
        )
    finally:
        server.close()
