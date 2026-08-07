"""Current-process collector health must fail closed and expose no evidence."""

import hashlib
import json
import signal
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from tradingagents import collector_health, poller
from tradingagents.collector_health import (
    CollectorHealthServer,
    CollectorHealthState,
)

STATIC_SLOTS = [
    {"provider": "globalnews", "query_key": f"theme-{index}:query"}
    for index in range(10)
]
STATIC_SLOT_IDS = {
    hashlib.sha256(
        f"{slot['provider']}\0{slot['query_key']}".encode()
    ).hexdigest()[:16]
    for slot in STATIC_SLOTS
}


def _complete_coverage(*, dynamic: bool = False):
    slots = list(STATIC_SLOTS)
    if dynamic:
        slots.append({"provider": "x", "query_key": "discovered topic"})
    return {"complete": True, "missing_query_slots": [], "query_slots": slots}


@pytest.mark.unit
def test_health_state_requires_current_process_cycle_and_fails_closed():
    revision = "a" * 40
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
        build_revision=revision,
        machine_id="machine-123",
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
    }

    # A boolean supplied by malformed orchestration cannot stand in for the
    # exact static slot manifest.
    state.mark_cycle(
        {"complete": True, "missing_query_slots": []},
        completed_utc=110.0,
        completed_monotonic=110.0,
    )
    status, malformed = state.snapshot(monotonic_now=120.0)
    assert status == 503
    assert malformed["reason"] == "coverage_incomplete"
    assert malformed["missing_query_slot_count"] == 10

    # Dynamic X slots may extend, but never replace, that static manifest.
    state.mark_cycle(
        _complete_coverage(dynamic=True),
        completed_utc=110.0,
        completed_monotonic=110.0,
    )
    status, healthy = state.snapshot(monotonic_now=120.0)
    assert status == 200
    assert healthy["reason"] == "healthy"
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
def test_health_http_endpoint_is_private_projection_only():
    state = CollectorHealthState(
        max_age_seconds=60.0,
        expected_query_slot_ids=STATIC_SLOT_IDS,
    )
    server = CollectorHealthServer(state, host="127.0.0.1", port=0)
    try:
        url = f"http://127.0.0.1:{server.port}/healthz"
        with pytest.raises(HTTPError) as exc_info:
            urlopen(url, timeout=2.0)  # noqa: S310 - loopback test server
        assert exc_info.value.code == 503
        starting = json.loads(exc_info.value.read())
        assert starting["reason"] == "starting"

        state.mark_cycle(
            _complete_coverage(),
            completed_utc=10**10,
        )
        with urlopen(url, timeout=2.0) as response:  # noqa: S310 - loopback test server
            assert response.status == 200
            payload = json.load(response)
        assert payload["status"] == "ok"
        assert "query_key" not in payload
        assert "url" not in payload

        with pytest.raises(HTTPError) as missing:
            urlopen(  # noqa: S310 - loopback test server
                f"http://127.0.0.1:{server.port}/not-health", timeout=2.0
            )
        assert missing.value.code == 404
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
            poller.poll_forever(
                object(), [], [], 3600, {}, health_state=state
            )
    else:
        poller.poll_forever(
            object(), [], [], 3600, {}, health_state=state
        )

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
        poller.poll_forever(
            object(), [], [], 3600, {}, health_state=state
        )

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
        "missing_periodic_requirements": [{"provider": "x", "period": "daily"}],
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
