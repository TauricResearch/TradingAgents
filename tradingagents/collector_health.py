"""Private, dependency-free health endpoints for the collector worker.

Both endpoints report only state produced by this process.  Readiness proves a
fresh cycle reached a normal return; strict health additionally requires full
coverage.  Receipts from a previous image cannot satisfy either endpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import threading
import time
from collections.abc import Mapping, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

_READINESS_RESPONSE_MAX_BYTES = 4096
_BUILD_REVISION = re.compile(r"[0-9a-f]{40}")
_MACHINE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_DEPLOYMENT_NONCE = re.compile(r"[0-9a-f]{32}")
_READY_PAYLOAD_KEYS = {
    "schema_version",
    "status",
    "reason",
    "expected_query_slot_count",
    "missing_query_slot_count",
    "missing_periodic_requirement_count",
    "missing_requirement_count",
    "last_cycle_age_seconds",
    "build_revision",
    "machine_id",
    "deployment_nonce",
}


def _finite_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


class CollectorHealthState:
    """Thread-safe projection of the current worker's last collection cycle."""

    def __init__(
        self,
        *,
        max_age_seconds: float,
        expected_query_slot_ids: set[str] | frozenset[str],
        build_revision: str | None = None,
        machine_id: str | None = None,
        deployment_nonce: str | None = None,
    ):
        if not _finite_number(max_age_seconds) or max_age_seconds <= 0:
            raise ValueError("collector health max age must be positive and finite")
        if not isinstance(expected_query_slot_ids, (set, frozenset)):
            raise ValueError("collector health query-slot IDs must be a set")
        if not expected_query_slot_ids or any(
            not isinstance(slot_id, str) or re.fullmatch(r"[0-9a-f]{16}", slot_id) is None
            for slot_id in expected_query_slot_ids
        ):
            raise ValueError("collector health query-slot IDs must be nonempty hashes")
        if build_revision is not None and (
            not isinstance(build_revision, str) or _BUILD_REVISION.fullmatch(build_revision) is None
        ):
            raise ValueError("collector health build revision must be a full Git SHA")
        if machine_id is not None and (
            not isinstance(machine_id, str) or _MACHINE_ID.fullmatch(machine_id) is None
        ):
            raise ValueError("collector health machine ID is invalid")
        if deployment_nonce is not None and (
            not isinstance(deployment_nonce, str)
            or _DEPLOYMENT_NONCE.fullmatch(deployment_nonce) is None
        ):
            raise ValueError("collector health deployment nonce is invalid")
        if machine_id is not None and (build_revision is None or deployment_nonce is None):
            raise ValueError("collector health Fly process identity must be complete")
        self.max_age_seconds = float(max_age_seconds)
        self.expected_query_slot_ids = frozenset(expected_query_slot_ids)
        self.build_revision = build_revision
        self.machine_id = machine_id
        self.deployment_nonce = deployment_nonce
        self._lock = threading.Lock()
        self._last_completed_monotonic: float | None = None
        self._expected_query_slots = len(self.expected_query_slot_ids)
        self._coverage_complete = False
        self._missing_query_slots = len(self.expected_query_slot_ids)
        self._missing_periodic_requirements = 0
        self._failure_type: str | None = None

    def mark_cycle(
        self,
        coverage: dict[str, Any],
        *,
        completed_utc: float,
        completed_monotonic: float | None = None,
    ) -> None:
        """Publish a terminal cycle projection without retaining query text."""
        if not isinstance(coverage, dict):
            raise ValueError("collector health coverage must be a mapping")
        if not _finite_number(completed_utc):
            raise ValueError("collector health completion time must be finite")
        monotonic_value = time.monotonic() if completed_monotonic is None else completed_monotonic
        if not _finite_number(monotonic_value):
            raise ValueError("collector health monotonic time must be finite")
        monotonic_value = float(monotonic_value)

        if not isinstance(coverage.get("complete"), bool):
            raise ValueError("collector health coverage completeness is invalid")
        query_slots = _coverage_query_slots(coverage, "query_slots")
        missing = _coverage_query_slots(coverage, "missing_query_slots")
        missing_periodic = _coverage_periodic_requirements(coverage)
        query_slot_states = {
            (slot["provider"], slot["query_key"]): _query_slot_health(slot) for slot in query_slots
        }
        missing_slot_reasons = {
            (slot["provider"], slot["query_key"]): _missing_slot_reason(slot) for slot in missing
        }
        unhealthy_slot_reasons = {
            pair: reason for pair, (healthy, reason) in query_slot_states.items() if not healthy
        }
        if missing_slot_reasons != unhealthy_slot_reasons:
            raise ValueError(
                "collector health missing query slots do not match unhealthy query slots"
            )
        missing_count = len(missing)
        missing_periodic_count = len(missing_periodic)
        observed_slot_ids = {
            _query_slot_id(slot["provider"], slot["query_key"]) for slot in query_slots
        }
        absent_static_slots = self.expected_query_slot_ids - observed_slot_ids
        if absent_static_slots:
            raise ValueError("collector health coverage omitted required query slots")
        complete = missing_count == 0 and missing_periodic_count == 0
        if coverage["complete"] != complete:
            raise ValueError("collector health coverage completeness contradicts requirements")
        with self._lock:
            self._last_completed_monotonic = monotonic_value
            self._expected_query_slots = len(query_slots)
            self._coverage_complete = complete
            self._missing_query_slots = missing_count
            self._missing_periodic_requirements = missing_periodic_count
            self._failure_type = None

    def mark_failure(self, failure_type: str) -> None:
        """Make the endpoint fail closed after an unhandled cycle exception."""
        safe_type = (
            failure_type
            if isinstance(failure_type, str)
            and failure_type.isidentifier()
            and len(failure_type) <= 64
            else "Exception"
        )
        with self._lock:
            self._coverage_complete = False
            self._failure_type = safe_type

    def snapshot(self, *, monotonic_now: float | None = None) -> tuple[int, dict[str, Any]]:
        """Return strict coverage health for ``/healthz``."""
        return self._snapshot(monotonic_now=monotonic_now, require_coverage=True)

    def readiness_snapshot(
        self, *, monotonic_now: float | None = None
    ) -> tuple[int, dict[str, Any]]:
        """Return runtime readiness for ``/readyz``."""
        return self._snapshot(monotonic_now=monotonic_now, require_coverage=False)

    def _snapshot(
        self,
        *,
        monotonic_now: float | None,
        require_coverage: bool,
    ) -> tuple[int, dict[str, Any]]:
        observed = time.monotonic() if monotonic_now is None else monotonic_now
        if not _finite_number(observed):
            raise ValueError("collector health monotonic observation must be finite")
        observed = float(observed)
        with self._lock:
            completed = self._last_completed_monotonic
            expected = self._expected_query_slots
            complete = self._coverage_complete
            missing = self._missing_query_slots
            missing_periodic = self._missing_periodic_requirements
            failure_type = self._failure_type

        age = None if completed is None else observed - completed
        valid_age = age is not None and _finite_number(age) and age >= 0
        if failure_type is not None:
            reason = "cycle_failed"
        elif completed is None:
            reason = "starting"
        elif require_coverage and not complete:
            reason = "coverage_incomplete"
        elif not valid_age or age > self.max_age_seconds:
            reason = "stale"
        else:
            reason = "healthy" if require_coverage else "ready"
        ok = reason in {"healthy", "ready"}
        payload: dict[str, Any] = {
            "schema_version": 1,
            "status": "ok" if ok else "unhealthy",
            "reason": reason,
            "expected_query_slot_count": expected,
            "missing_query_slot_count": missing,
            "missing_periodic_requirement_count": missing_periodic,
            "missing_requirement_count": missing + missing_periodic,
            "last_cycle_age_seconds": round(age, 3) if valid_age else None,
        }
        if self.build_revision is not None:
            payload["build_revision"] = self.build_revision
        if self.machine_id is not None:
            payload["machine_id"] = self.machine_id
        if self.deployment_nonce is not None:
            payload["deployment_nonce"] = self.deployment_nonce
        if failure_type is not None:
            payload["failure_type"] = failure_type
        return (200 if ok else 503), payload


def _query_slot_id(provider: str, query_key: str) -> str:
    """Return the non-reversible identifier used by collector coverage logs."""
    material = f"{provider}\0{query_key}".encode()
    return hashlib.sha256(material).hexdigest()[:16]


def _coverage_query_slots(coverage: Mapping[str, Any], field: str) -> list[Mapping[str, Any]]:
    """Return one required, unique list of exact query-slot mappings."""
    slots = coverage.get(field)
    if not isinstance(slots, list):
        raise ValueError(f"collector health {field} must be a list")
    pairs: set[tuple[str, str]] = set()
    for slot in slots:
        if not isinstance(slot, Mapping):
            raise ValueError(f"collector health {field} entries must be mappings")
        provider = slot.get("provider")
        query_key = slot.get("query_key")
        if (
            not isinstance(provider, str)
            or not provider.strip()
            or not isinstance(query_key, str)
            or not query_key.strip()
        ):
            raise ValueError(f"collector health {field} entries are invalid")
        pair = (provider, query_key)
        if pair in pairs:
            raise ValueError(f"collector health {field} entries must be unique")
        pairs.add(pair)
    return slots


def _coverage_periodic_requirements(coverage: Mapping[str, Any]) -> list[str]:
    """Return the required, unique periodic-requirement names."""
    requirements = coverage.get("missing_periodic_requirements")
    if not isinstance(requirements, list) or any(
        not isinstance(name, str) or not name.strip() for name in requirements
    ):
        raise ValueError("collector health missing_periodic_requirements must be a string list")
    if len(requirements) != len(set(requirements)):
        raise ValueError("collector health missing_periodic_requirements must be unique")
    return requirements


def _query_slot_health(slot: Mapping[str, Any]) -> tuple[bool, str | None]:
    healthy = slot.get("healthy")
    reason = slot.get("reason")
    if (
        not isinstance(healthy, bool)
        or (healthy and reason is not None)
        or (not healthy and (not isinstance(reason, str) or not reason.strip()))
    ):
        raise ValueError("collector health query slot state is invalid")
    return healthy, reason


def _missing_slot_reason(slot: Mapping[str, Any]) -> str:
    reason = slot.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("collector health missing query slot reason is invalid")
    return reason


class _CollectorHealthHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], state: CollectorHealthState):
        self.state = state
        super().__init__(address, _CollectorHealthHandler)


class _CollectorHealthHandler(BaseHTTPRequestHandler):
    server: _CollectorHealthHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/healthz":
            snapshot = self.server.state.snapshot
        elif self.path == "/readyz":
            snapshot = self.server.state.readiness_snapshot
        else:
            self._write_json(404, {"status": "not_found"})
            return
        status, payload = snapshot()
        self._write_json(status, payload)

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
        except ConnectionError:
            # Health clients are allowed to disconnect after sending a probe.
            return

    def log_message(self, _format: str, *_args: object) -> None:
        """Do not add one access-log line for every Fly health probe."""


class CollectorHealthServer:
    """Lifecycle wrapper around the private HTTP server thread."""

    def __init__(self, state: CollectorHealthState, *, host: str, port: int):
        if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
            raise ValueError("collector health port must be between 0 and 65535")
        self._server = _CollectorHealthHTTPServer((host, port), state)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="collector-health",
            daemon=True,
        )
        self._thread.start()

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5.0)


def start_collector_health_server(
    state: CollectorHealthState, *, port: int, host: str = "0.0.0.0"
) -> CollectorHealthServer:
    """Start the private health listener, raising if its configured port is unusable."""
    return CollectorHealthServer(state, host=host, port=port)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("collector readiness JSON keys must be unique")
        value[key] = item
    return value


def _reject_json_constant(_value: str) -> None:
    raise ValueError("collector readiness JSON constants must be finite")


def probe_collector_readiness(
    *,
    expected_build_revision: str,
    expected_machine_id: str,
    expected_deployment_nonce: str,
    port: int,
    timeout_seconds: float = 5.0,
) -> bool:
    """Verify the exact local collector process without exposing its response."""
    if (
        not isinstance(expected_build_revision, str)
        or _BUILD_REVISION.fullmatch(expected_build_revision) is None
    ):
        raise ValueError("collector readiness revision must be a full Git SHA")
    if (
        not isinstance(expected_machine_id, str)
        or _MACHINE_ID.fullmatch(expected_machine_id) is None
    ):
        raise ValueError("collector readiness machine ID is invalid")
    if (
        not isinstance(expected_deployment_nonce, str)
        or _DEPLOYMENT_NONCE.fullmatch(expected_deployment_nonce) is None
    ):
        raise ValueError("collector readiness deployment nonce is invalid")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("collector readiness port must be between 1 and 65535")
    if not _finite_number(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("collector readiness timeout must be positive and finite")

    request = Request(  # noqa: S310 - URL is fixed to this process's loopback
        f"http://127.0.0.1:{port}/readyz",
        headers={"Accept": "application/json", "Connection": "close"},
    )
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=float(timeout_seconds)) as response:  # noqa: S310
            if response.status != 200:
                return False
            content_type = response.headers.get("Content-Type")
            if (
                not isinstance(content_type, str)
                or content_type.partition(";")[0].strip().lower() != "application/json"
            ):
                return False
            content_length = response.headers.get("Content-Length")
            if (
                not isinstance(content_length, str)
                or not content_length.isascii()
                or not content_length.isdecimal()
            ):
                return False
            declared_length = int(content_length)
            if declared_length > _READINESS_RESPONSE_MAX_BYTES:
                return False
            body = response.read(_READINESS_RESPONSE_MAX_BYTES + 1)
            if len(body) != declared_length or len(body) > _READINESS_RESPONSE_MAX_BYTES:
                return False
        payload = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (
        HTTPError,
        URLError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        OverflowError,
        RecursionError,
        TypeError,
        ValueError,
    ):
        return False
    if not isinstance(payload, dict) or set(payload) != _READY_PAYLOAD_KEYS:
        return False
    count_fields = (
        "expected_query_slot_count",
        "missing_query_slot_count",
        "missing_periodic_requirement_count",
        "missing_requirement_count",
    )
    if any(type(payload[field]) is not int or payload[field] < 0 for field in count_fields):
        return False
    age = payload["last_cycle_age_seconds"]
    return bool(
        type(payload["schema_version"]) is int
        and payload["schema_version"] == 1
        and payload["status"] == "ok"
        and payload["reason"] == "ready"
        and payload["expected_query_slot_count"] > 0
        and payload["missing_query_slot_count"]
        <= payload["expected_query_slot_count"]
        and payload["missing_requirement_count"]
        == payload["missing_query_slot_count"] + payload["missing_periodic_requirement_count"]
        and _finite_number(age)
        and age >= 0
        and payload["build_revision"] == expected_build_revision
        and payload["machine_id"] == expected_machine_id
        and payload["deployment_nonce"] == expected_deployment_nonce
    )


def readiness_probe_main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Run the silent loopback readiness verifier used by production deploys."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--expected-build-revision", required=True)
    parser.add_argument("--expected-machine-id", required=True)
    parser.add_argument("--expected-deployment-nonce", required=True)
    try:
        args = parser.parse_args(argv)
        values = os.environ if environ is None else environ
        raw_port = values.get("MEDIA_HEALTH_PORT", "")
        if not isinstance(raw_port, str) or not raw_port.isascii() or not raw_port.isdecimal():
            return 1
        return (
            0
            if probe_collector_readiness(
                expected_build_revision=args.expected_build_revision,
                expected_machine_id=args.expected_machine_id,
                expected_deployment_nonce=args.expected_deployment_nonce,
                port=int(raw_port),
            )
            else 1
        )
    except (SystemExit, TypeError, ValueError):
        return 1


if __name__ == "__main__":
    raise SystemExit(readiness_probe_main())
