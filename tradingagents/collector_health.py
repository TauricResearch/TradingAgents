"""Private, dependency-free health endpoint for the collector worker.

The endpoint deliberately reports only state produced by this process.  A newly
deployed image therefore stays unhealthy until *it* completes a collection
cycle; recent receipts from the previous image cannot make a broken release
look healthy.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class CollectorHealthState:
    """Thread-safe projection of the current worker's last collection cycle."""

    def __init__(
        self,
        *,
        max_age_seconds: float,
        expected_query_slot_ids: set[str] | frozenset[str],
        build_revision: str | None = None,
        machine_id: str | None = None,
    ):
        if not math.isfinite(max_age_seconds) or max_age_seconds <= 0:
            raise ValueError("collector health max age must be positive and finite")
        if not isinstance(expected_query_slot_ids, (set, frozenset)):
            raise ValueError("collector health query-slot IDs must be a set")
        if not expected_query_slot_ids or any(
            not isinstance(slot_id, str)
            or re.fullmatch(r"[0-9a-f]{16}", slot_id) is None
            for slot_id in expected_query_slot_ids
        ):
            raise ValueError("collector health query-slot IDs must be nonempty hashes")
        if build_revision is not None and re.fullmatch(
            r"[0-9a-f]{40}", build_revision
        ) is None:
            raise ValueError("collector health build revision must be a full Git SHA")
        if machine_id is not None and re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", machine_id
        ) is None:
            raise ValueError("collector health machine ID is invalid")
        self.max_age_seconds = float(max_age_seconds)
        self.expected_query_slot_ids = frozenset(expected_query_slot_ids)
        self.build_revision = build_revision
        self.machine_id = machine_id
        self._lock = threading.Lock()
        self._last_completed_utc: float | None = None
        self._last_completed_monotonic: float | None = None
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
        if not math.isfinite(completed_utc):
            raise ValueError("collector health completion time must be finite")
        monotonic_value = (
            time.monotonic()
            if completed_monotonic is None
            else float(completed_monotonic)
        )
        if not math.isfinite(monotonic_value):
            raise ValueError("collector health monotonic time must be finite")
        missing = coverage.get("missing_query_slots")
        missing_count = len(missing) if isinstance(missing, list) else int(missing is not None)
        missing_periodic = coverage.get("missing_periodic_requirements")
        missing_periodic_count = (
            len(missing_periodic)
            if isinstance(missing_periodic, list)
            else int(missing_periodic is not None)
        )
        query_slots = coverage.get("query_slots")
        observed_slot_ids = {
            _query_slot_id(slot.get("provider"), slot.get("query_key"))
            for slot in query_slots
            if isinstance(slot, dict)
            and isinstance(slot.get("provider"), str)
            and isinstance(slot.get("query_key"), str)
        } if isinstance(query_slots, list) else set()
        absent_static_slots = self.expected_query_slot_ids - observed_slot_ids
        complete = (
            bool(coverage.get("complete"))
            and missing_count == 0
            and missing_periodic_count == 0
            and not absent_static_slots
        )
        with self._lock:
            self._last_completed_utc = float(completed_utc)
            self._last_completed_monotonic = monotonic_value
            self._coverage_complete = complete
            self._missing_query_slots = missing_count + len(absent_static_slots)
            self._missing_periodic_requirements = missing_periodic_count
            self._failure_type = None

    def mark_failure(self, failure_type: str) -> None:
        """Make the endpoint fail closed after an unhandled cycle exception."""
        safe_type = (
            failure_type
            if failure_type.isidentifier() and len(failure_type) <= 64
            else "Exception"
        )
        with self._lock:
            self._coverage_complete = False
            self._failure_type = safe_type

    def snapshot(
        self, *, monotonic_now: float | None = None
    ) -> tuple[int, dict[str, Any]]:
        observed = time.monotonic() if monotonic_now is None else float(monotonic_now)
        if not math.isfinite(observed):
            raise ValueError("collector health monotonic observation must be finite")
        with self._lock:
            completed = self._last_completed_monotonic
            complete = self._coverage_complete
            missing = self._missing_query_slots
            missing_periodic = self._missing_periodic_requirements
            failure_type = self._failure_type

        age = None if completed is None else observed - completed
        if failure_type is not None:
            reason = "cycle_failed"
        elif completed is None:
            reason = "starting"
        elif not complete:
            reason = "coverage_incomplete"
        elif age is None or age < 0 or age > self.max_age_seconds:
            reason = "stale"
        else:
            reason = "healthy"
        healthy = reason == "healthy"
        payload: dict[str, Any] = {
            "schema_version": 1,
            "status": "ok" if healthy else "unhealthy",
            "reason": reason,
            "expected_query_slot_count": len(self.expected_query_slot_ids),
            "missing_query_slot_count": missing,
            "missing_periodic_requirement_count": missing_periodic,
            "missing_requirement_count": missing + missing_periodic,
            "last_cycle_age_seconds": (
                None if age is None or age < 0 else round(age, 3)
            ),
        }
        if self.build_revision is not None:
            payload["build_revision"] = self.build_revision
        if self.machine_id is not None:
            payload["machine_id"] = self.machine_id
        if failure_type is not None:
            payload["failure_type"] = failure_type
        return (200 if healthy else 503), payload


def _query_slot_id(provider: str, query_key: str) -> str:
    """Return the non-reversible identifier used by collector coverage logs."""
    material = f"{provider}\0{query_key}".encode()
    return hashlib.sha256(material).hexdigest()[:16]


class _CollectorHealthHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], state: CollectorHealthState):
        self.state = state
        super().__init__(address, _CollectorHealthHandler)


class _CollectorHealthHandler(BaseHTTPRequestHandler):
    server: _CollectorHealthHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/healthz":
            self._write_json(404, {"status": "not_found"})
            return
        status, payload = self.server.state.snapshot()
        self._write_json(status, payload)

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        """Do not add one access-log line for every Fly health probe."""


class CollectorHealthServer:
    """Lifecycle wrapper around the private HTTP server thread."""

    def __init__(self, state: CollectorHealthState, *, host: str, port: int):
        if isinstance(port, bool) or not 0 <= port <= 65535:
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
