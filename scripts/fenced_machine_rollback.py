#!/usr/bin/env python3
"""Conditionally restore one stateless Fly Machine under an exclusive lease.

The caller authenticates both the current candidate and a saved baseline tuple.
This helper acquires a bounded Machine lease, revalidates the current Machine and
single-Machine topology, submits one digest-pinned update, and verifies the exact
result with fresh GETs before releasing the lease. It never retries the mutating
request or prints API response bodies, credentials, identifiers, or file paths.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

_API_BASE = "https://api.machines.dev"
_REQUEST_TIMEOUT_SECONDS = 20
_MAX_RESPONSE_BYTES = 2_000_000

# A Machine update can include a reboot. Ten minutes is deliberately finite but
# leaves ample room for the bounded preflight, update, reconciliation, and release
# requests below. We refuse a lease whose returned expiry is unexpectedly short
# or materially longer than requested.
_LEASE_SECONDS = 600
_MIN_LEASE_REMAINING_SECONDS = 300
_LEASE_CLOCK_SKEW_SECONDS = 60
_VERIFY_ATTEMPTS = 5
_VERIFY_INTERVAL_SECONDS = 2
_VERIFIED_RELEASE_MARGIN_SECONDS = _REQUEST_TIMEOUT_SECONDS + 10
_POST_UPDATE_MARGIN_SECONDS = (
    _VERIFY_ATTEMPTS * _REQUEST_TIMEOUT_SECONDS
    + (_VERIFY_ATTEMPTS - 1) * _VERIFY_INTERVAL_SECONDS
    + _REQUEST_TIMEOUT_SECONDS
    + _VERIFIED_RELEASE_MARGIN_SECONDS
)
_PRE_UPDATE_MARGIN_SECONDS = _REQUEST_TIMEOUT_SECONDS + _POST_UPDATE_MARGIN_SECONDS

_ROLLBACK_PREFIX = "tradingagents_fenced_rollback_"
_ROLLBACK_FROM = f"{_ROLLBACK_PREFIX}from_release_version"
_ROLLBACK_TO = f"{_ROLLBACK_PREFIX}to_release_version"
_ROLLBACK_SCHEMA = f"{_ROLLBACK_PREFIX}schema_version"
_ROLLBACK_OPERATION = f"{_ROLLBACK_PREFIX}operation_id"
_ROLLBACK_RECORDED_AT = f"{_ROLLBACK_PREFIX}recorded_at"
_ROLLBACK_FROM_MACHINE = f"{_ROLLBACK_PREFIX}from_machine_id"
_ROLLBACK_FROM_INSTANCE = f"{_ROLLBACK_PREFIX}from_instance_id"
_ROLLBACK_FROM_RELEASE = f"{_ROLLBACK_PREFIX}from_release_id"
_ROLLBACK_FROM_DIGEST = f"{_ROLLBACK_PREFIX}from_image_digest"
_ROLLBACK_FROM_CONFIG = f"{_ROLLBACK_PREFIX}from_config_fingerprint"
_ROLLBACK_TO_MACHINE = f"{_ROLLBACK_PREFIX}to_machine_id"
_ROLLBACK_TO_INSTANCE = f"{_ROLLBACK_PREFIX}to_instance_id"
_ROLLBACK_TO_RELEASE = f"{_ROLLBACK_PREFIX}to_release_id"
_ROLLBACK_TO_DIGEST = f"{_ROLLBACK_PREFIX}to_image_digest"
_ROLLBACK_TO_CONFIG = f"{_ROLLBACK_PREFIX}to_config_fingerprint"
_ROLLBACK_PARENT = f"{_ROLLBACK_PREFIX}parent_lineage_sha256"
_ROLLBACK_BASELINE_STATUS = f"{_ROLLBACK_PREFIX}baseline_status_sha256"

_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{8,128}")
_RELEASE_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}")
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}")
_VERSION_PATTERN = re.compile(r"[1-9][0-9]*")
_LINEAGE_VERSION_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)")


class FencedRollbackError(RuntimeError):
    """A sanitized rollback contract failure."""


class OwnershipChanged(FencedRollbackError):
    """The leased Machine is no longer the authenticated candidate."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _SanitizedParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise FencedRollbackError("rollback arguments are invalid")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _reject_json_constant(_value: str) -> None:
    raise ValueError


def _config_fingerprint(config: dict[str, Any]) -> str:
    # This intentionally matches the deploy wrapper's established fingerprint.
    # Release and rollback metadata are authenticated separately as explicit
    # tuple fields and are also compared exactly across the two API snapshots.
    semantic = {key: value for key, value in config.items() if key not in {"image", "metadata"}}
    return _sha256_json(semantic)


def _request_json(
    opener,
    *,
    token: str,
    method: str,
    url: str,
    expected_status: int,
    payload: dict[str, Any] | None = None,
    lease_nonce: str | None = None,
) -> Any:
    body = None if payload is None else _canonical_json(payload)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    if lease_nonce is not None:
        headers["fly-machine-lease-nonce"] = lease_nonce
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            if response.status != expected_status or response.geturl() != url:
                raise FencedRollbackError("unexpected Fly API response")
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except (HTTPError, HTTPException, URLError, TimeoutError, OSError) as exc:
        raise FencedRollbackError("Fly API request failed") from exc
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise FencedRollbackError("Fly API response was oversized")
    try:
        return json.loads(raw, parse_constant=_reject_json_constant)
    except (TypeError, ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise FencedRollbackError("Fly API response was malformed") from exc


def _require_reference(value: Any, message: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 1024
        or not value.isascii()
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise FencedRollbackError(message)
    return value


def _require_complete_stateless_config(
    machine: Any,
    *,
    error_type: type[FencedRollbackError],
    message: str,
    allow_legacy_on_failure: bool = False,
) -> dict[str, Any]:
    if not isinstance(machine, dict):
        raise error_type(message)
    if machine.get("host_status") != "ok":
        raise error_type(message)
    incomplete = machine.get("incomplete_config")
    if incomplete is not None and incomplete is not False:
        raise error_type(message)
    config = machine.get("config")
    if not isinstance(config, dict) or not config:
        raise error_type(message)

    expected_sections = {
        "metadata": dict,
        "env": dict,
        "guest": dict,
        "init": dict,
        "restart": dict,
    }
    if any(not isinstance(config.get(key), kind) for key, kind in expected_sections.items()):
        raise error_type(message)
    try:
        _require_reference(config.get("image"), message)
    except FencedRollbackError as exc:
        raise error_type(message) from exc

    metadata = config["metadata"]
    env = config["env"]
    if any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in metadata.items()
    ):
        raise error_type(message)
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in env.items()):
        raise error_type(message)
    process_group = metadata.get("fly_process_group") or env.get("FLY_PROCESS_GROUP")
    restart = config["restart"]
    restart_policy = restart.get("policy")
    legacy_restart_is_valid = (
        allow_legacy_on_failure
        and restart_policy == "on-failure"
        and not isinstance(restart.get("max_retries"), bool)
        and isinstance(restart.get("max_retries"), int)
        and 1 <= restart["max_retries"] <= 100
    )
    if process_group != "app" or (restart_policy != "always" and not legacy_restart_is_valid):
        raise error_type(message)

    # The in-place rollback model is only safe for this stateless collector.
    # Empty/absent arrays are harmless, but mounted volumes and injected files
    # require workload-specific recovery semantics and are rejected.
    for key in ("mounts", "files"):
        if config.get(key) not in (None, []):
            raise error_type(message)
    return config


def _machine_digest(
    machine: dict[str, Any],
    *,
    error_type: type[FencedRollbackError],
    message: str,
) -> str:
    image_ref = machine.get("image_ref")
    digest = image_ref.get("digest") if isinstance(image_ref, dict) else None
    if not isinstance(digest, str) or _DIGEST_PATTERN.fullmatch(digest) is None:
        raise error_type(message)
    return digest


def _app_machine(
    payload: Any,
    *,
    allow_legacy_baseline_on_failure: bool,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise FencedRollbackError("saved status is malformed")
    machines = payload.get("Machines")
    if not isinstance(machines, list) or len(machines) != 1:
        raise FencedRollbackError("saved baseline violates single-Machine policy")
    machine = machines[0]
    _require_complete_stateless_config(
        machine,
        error_type=FencedRollbackError,
        message="saved baseline Machine is incomplete or stateful",
        allow_legacy_on_failure=allow_legacy_baseline_on_failure,
    )
    if machine.get("state") != "started":
        raise FencedRollbackError("saved baseline Machine is not started")
    return machine


def _single_api_machine(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise OwnershipChanged("current app violates single-Machine policy")
    return payload[0]


def _machine_snapshot(machine: dict[str, Any]) -> tuple[Any, ...]:
    return (
        machine.get("id"),
        machine.get("instance_id"),
        machine.get("state"),
        machine.get("host_status"),
        machine.get("incomplete_config"),
        _machine_digest(
            machine,
            error_type=OwnershipChanged,
            message="current Machine image identity is incomplete",
        ),
        machine.get("config"),
    )


def _validate_current_machine(machine: Any, args: argparse.Namespace) -> dict[str, Any]:
    config = _require_complete_stateless_config(
        machine,
        error_type=OwnershipChanged,
        message="candidate Machine is incomplete or stateful",
    )
    metadata = config["metadata"]
    identity = (
        machine.get("id"),
        machine.get("instance_id"),
        machine.get("state"),
        config.get("image"),
        _machine_digest(
            machine,
            error_type=OwnershipChanged,
            message="candidate Machine image identity is incomplete",
        ),
        metadata.get("fly_release_id"),
        metadata.get("fly_release_version"),
        metadata.get(_ROLLBACK_FROM, "0"),
        metadata.get(_ROLLBACK_TO, "0"),
        _config_fingerprint(config),
    )
    expected = (
        args.machine_id,
        args.expected_instance,
        "started",
        args.expected_image,
        args.expected_digest,
        args.expected_release,
        args.expected_release_version,
        args.expected_rollback_from_version,
        args.expected_rollback_to_version,
        args.expected_config_fingerprint,
    )
    if identity != expected:
        raise OwnershipChanged("candidate Machine ownership changed")
    return config


def _validate_restored_machine(
    machine: Any,
    *,
    args: argparse.Namespace,
    expected_config: dict[str, Any],
) -> None:
    config = _require_complete_stateless_config(
        machine,
        error_type=FencedRollbackError,
        message="restored Machine is incomplete or stateful",
        allow_legacy_on_failure=args.allow_legacy_baseline_on_failure,
    )
    instance = machine.get("instance_id")
    if (
        machine.get("id") != args.machine_id
        or machine.get("state") != "started"
        or not isinstance(instance, str)
        or _ID_PATTERN.fullmatch(instance) is None
        or instance in {args.expected_instance, args.baseline_instance}
        or _machine_digest(
            machine,
            error_type=FencedRollbackError,
            message="restored Machine image identity is incomplete",
        )
        != args.baseline_digest
        or config != expected_config
    ):
        raise FencedRollbackError("Fly Machine rollback outcome did not match the baseline")


def _pin_image(image: str, digest: str) -> str:
    if "@" in image:
        name, existing_digest = image.rsplit("@", 1)
        if not name or existing_digest != digest:
            raise FencedRollbackError("saved baseline image pin is inconsistent")
        return image
    return f"{image}@{digest}"


def _validate_args(args: argparse.Namespace) -> str:
    token = (os.environ.get("FLY_API_TOKEN") or "").strip()
    if not token or len(token) > 4096 or any(character.isspace() for character in token):
        raise FencedRollbackError("Fly API token is unavailable")
    if not isinstance(args.app, str) or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", args.app) is None:
        raise FencedRollbackError("Fly app name is invalid")
    for value in (
        args.machine_id,
        args.expected_instance,
        args.baseline_machine_id,
        args.baseline_instance,
    ):
        if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
            raise FencedRollbackError("Fly Machine identity is invalid")
    if (
        args.machine_id != args.baseline_machine_id
        or args.expected_instance == args.baseline_instance
    ):
        raise FencedRollbackError("rollback Machine lineage is invalid")
    for value in (args.expected_image, args.baseline_image):
        _require_reference(value, "Fly image reference is invalid")
    for value in (args.expected_digest, args.baseline_digest):
        if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
            raise FencedRollbackError("Fly image digest is invalid")
    for value in (args.expected_release, args.baseline_release):
        if not isinstance(value, str) or _RELEASE_PATTERN.fullmatch(value) is None:
            raise FencedRollbackError("Fly release identity is invalid")
    for value in (args.expected_release_version, args.baseline_release_version):
        if not isinstance(value, str) or _VERSION_PATTERN.fullmatch(value) is None:
            raise FencedRollbackError("Fly release version is invalid")
    if int(args.baseline_release_version) >= int(args.expected_release_version):
        raise FencedRollbackError("rollback release order is invalid")
    for value in (args.expected_rollback_from_version, args.expected_rollback_to_version):
        if not isinstance(value, str) or _LINEAGE_VERSION_PATTERN.fullmatch(value) is None:
            raise FencedRollbackError("candidate rollback lineage is invalid")
    for value in (args.expected_config_fingerprint, args.baseline_config_fingerprint):
        if not isinstance(value, str) or _FINGERPRINT_PATTERN.fullmatch(value) is None:
            raise FencedRollbackError("Machine config fingerprint is invalid")
    if not isinstance(args.allow_legacy_baseline_on_failure, bool):
        raise FencedRollbackError("legacy baseline policy is invalid")
    return token


def _wall_time(clock) -> float:
    value = clock()
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise FencedRollbackError("local lease clock is unavailable")
    return float(value)


def _recorded_at(epoch: float) -> str:
    try:
        return (
            datetime.fromtimestamp(epoch, tz=timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    except (OverflowError, OSError, ValueError) as exc:
        raise FencedRollbackError("local lease clock is unavailable") from exc


def _validate_lease_expiry(expires_at: Any, requested_at: float, received_at: float) -> int:
    if isinstance(expires_at, bool) or not isinstance(expires_at, int):
        raise FencedRollbackError("Fly Machine lease expiry was malformed")
    if expires_at - received_at < _MIN_LEASE_REMAINING_SECONDS:
        raise FencedRollbackError("Fly Machine lease was too short")
    if expires_at > requested_at + _LEASE_SECONDS + _LEASE_CLOCK_SKEW_SECONDS:
        raise FencedRollbackError("Fly Machine lease exceeded its requested bound")
    return expires_at


def _require_lease_margin(expires_at: int, clock, minimum: int) -> None:
    if expires_at - _wall_time(clock) < minimum:
        raise FencedRollbackError("Fly Machine lease no longer covers verification")


def _prepare_baseline(
    args: argparse.Namespace,
    *,
    captured_at: float,
) -> dict[str, Any]:
    try:
        raw_status = Path(args.previous_status).read_bytes()
    except OSError as exc:
        raise FencedRollbackError("saved baseline status is unavailable") from exc
    if len(raw_status) > _MAX_RESPONSE_BYTES:
        raise FencedRollbackError("saved baseline status is oversized")
    try:
        previous_payload = json.loads(raw_status, parse_constant=_reject_json_constant)
    except (TypeError, ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise FencedRollbackError("saved baseline status is unavailable") from exc

    previous_machine = _app_machine(
        previous_payload,
        allow_legacy_baseline_on_failure=args.allow_legacy_baseline_on_failure,
    )
    previous_config = _require_complete_stateless_config(
        previous_machine,
        error_type=FencedRollbackError,
        message="saved baseline Machine is incomplete or stateful",
        allow_legacy_on_failure=args.allow_legacy_baseline_on_failure,
    )
    previous_metadata = previous_config["metadata"]
    baseline_identity = (
        previous_machine.get("id"),
        previous_machine.get("instance_id"),
        previous_machine.get("state"),
        previous_config.get("image"),
        _machine_digest(
            previous_machine,
            error_type=FencedRollbackError,
            message="saved baseline image identity is incomplete",
        ),
        previous_metadata.get("fly_release_id"),
        previous_metadata.get("fly_release_version"),
        _config_fingerprint(previous_config),
    )
    expected_identity = (
        args.baseline_machine_id,
        args.baseline_instance,
        "started",
        args.baseline_image,
        args.baseline_digest,
        args.baseline_release,
        args.baseline_release_version,
        args.baseline_config_fingerprint,
    )
    if baseline_identity != expected_identity:
        raise FencedRollbackError("saved baseline identity is inconsistent")

    previous_config = copy.deepcopy(previous_config)
    metadata = previous_config["metadata"]
    prior_lineage = {
        key: value for key, value in metadata.items() if key.startswith(_ROLLBACK_PREFIX)
    }
    parent_hash = _sha256_json(prior_lineage) if prior_lineage else "0" * 64
    baseline_status_hash = hashlib.sha256(raw_status).hexdigest()
    timestamp = _recorded_at(captured_at)
    lineage_seed = {
        "schema_version": "1",
        "recorded_at": timestamp,
        "baseline_status_sha256": baseline_status_hash,
        "parent_lineage_sha256": parent_hash,
        "from": {
            "machine_id": args.machine_id,
            "instance_id": args.expected_instance,
            "release_id": args.expected_release,
            "release_version": args.expected_release_version,
            "image_digest": args.expected_digest,
            "config_fingerprint": args.expected_config_fingerprint,
        },
        "to": {
            "machine_id": args.baseline_machine_id,
            "instance_id": args.baseline_instance,
            "release_id": args.baseline_release,
            "release_version": args.baseline_release_version,
            "image_digest": args.baseline_digest,
            "config_fingerprint": args.baseline_config_fingerprint,
        },
    }
    metadata.update(
        {
            _ROLLBACK_SCHEMA: "1",
            _ROLLBACK_OPERATION: _sha256_json(lineage_seed),
            _ROLLBACK_RECORDED_AT: timestamp,
            _ROLLBACK_FROM: args.expected_release_version,
            _ROLLBACK_TO: args.baseline_release_version,
            _ROLLBACK_FROM_MACHINE: args.machine_id,
            _ROLLBACK_FROM_INSTANCE: args.expected_instance,
            _ROLLBACK_FROM_RELEASE: args.expected_release,
            _ROLLBACK_FROM_DIGEST: args.expected_digest,
            _ROLLBACK_FROM_CONFIG: args.expected_config_fingerprint,
            _ROLLBACK_TO_MACHINE: args.baseline_machine_id,
            _ROLLBACK_TO_INSTANCE: args.baseline_instance,
            _ROLLBACK_TO_RELEASE: args.baseline_release,
            _ROLLBACK_TO_DIGEST: args.baseline_digest,
            _ROLLBACK_TO_CONFIG: args.baseline_config_fingerprint,
            _ROLLBACK_PARENT: parent_hash,
            _ROLLBACK_BASELINE_STATUS: baseline_status_hash,
        }
    )
    previous_config["image"] = _pin_image(args.baseline_image, args.baseline_digest)
    return previous_config


def _verify_restored_under_lease(
    *,
    opener,
    token: str,
    machine_url: str,
    machines_url: str,
    lease_nonce: str,
    lease_expires_at: int,
    args: argparse.Namespace,
    expected_config: dict[str, Any],
    clock,
    sleeper,
) -> None:
    last_error: FencedRollbackError | None = None
    for attempt in range(_VERIFY_ATTEMPTS):
        _require_lease_margin(
            lease_expires_at,
            clock,
            _REQUEST_TIMEOUT_SECONDS + _VERIFIED_RELEASE_MARGIN_SECONDS,
        )
        try:
            restored = _request_json(
                opener,
                token=token,
                method="GET",
                url=machine_url,
                expected_status=200,
                lease_nonce=lease_nonce,
            )
            _validate_restored_machine(
                restored,
                args=args,
                expected_config=expected_config,
            )
            listed_restored = _single_api_machine(
                _request_json(
                    opener,
                    token=token,
                    method="GET",
                    url=machines_url,
                    expected_status=200,
                )
            )
            _validate_restored_machine(
                listed_restored,
                args=args,
                expected_config=expected_config,
            )
            if _machine_snapshot(listed_restored) != _machine_snapshot(restored):
                raise FencedRollbackError("restored Machine changed during topology validation")
            return
        except FencedRollbackError as exc:
            last_error = exc
        if attempt + 1 < _VERIFY_ATTEMPTS:
            _require_lease_margin(
                lease_expires_at,
                clock,
                _VERIFY_INTERVAL_SECONDS
                + _REQUEST_TIMEOUT_SECONDS
                + _VERIFIED_RELEASE_MARGIN_SECONDS,
            )
            sleeper(_VERIFY_INTERVAL_SECONDS)
    raise FencedRollbackError(
        "Fly Machine rollback did not reach its exact started state"
    ) from last_error


def fenced_rollback(args: argparse.Namespace, *, opener=None, clock=None, sleeper=None) -> None:
    token = _validate_args(args)
    clock = time.time if clock is None else clock
    sleeper = time.sleep if sleeper is None else sleeper
    captured_at = _wall_time(clock)
    previous_config = _prepare_baseline(args, captured_at=captured_at)

    opener = build_opener(_NoRedirect) if opener is None else opener
    app = quote(args.app, safe="")
    machine_id = quote(args.machine_id, safe="")
    machines_url = f"{_API_BASE}/v1/apps/{app}/machines"
    machine_url = f"{machines_url}/{machine_id}"
    lease_url = f"{machine_url}/lease"
    lease_nonce = None
    lease_expires_at = None
    update_verified = False
    try:
        lease_requested_at = _wall_time(clock)
        lease = _request_json(
            opener,
            token=token,
            method="POST",
            url=lease_url,
            expected_status=201,
            payload={
                "description": "tradingagents conditional rollback",
                "ttl": _LEASE_SECONDS,
            },
        )
        lease_received_at = _wall_time(clock)
        if not isinstance(lease, dict):
            raise FencedRollbackError("Fly Machine lease was malformed")
        data = lease.get("data")
        lease_nonce = data.get("nonce") if isinstance(data, dict) else None
        lease_version = data.get("version") if isinstance(data, dict) else None
        expires_at = data.get("expires_at") if isinstance(data, dict) else None
        if (
            lease.get("status") != "success"
            or not isinstance(lease_nonce, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{8,256}", lease_nonce) is None
        ):
            lease_nonce = None
            raise FencedRollbackError("Fly Machine lease was malformed")
        lease_expires_at = _validate_lease_expiry(expires_at, lease_requested_at, lease_received_at)
        if lease_version != args.expected_instance:
            raise OwnershipChanged("candidate changed before lease acquisition")

        current = _request_json(
            opener,
            token=token,
            method="GET",
            url=machine_url,
            expected_status=200,
            lease_nonce=lease_nonce,
        )
        _validate_current_machine(current, args)
        listed_current = _single_api_machine(
            _request_json(
                opener,
                token=token,
                method="GET",
                url=machines_url,
                expected_status=200,
            )
        )
        _validate_current_machine(listed_current, args)
        if _machine_snapshot(listed_current) != _machine_snapshot(current):
            raise OwnershipChanged("candidate changed during topology validation")

        _require_lease_margin(lease_expires_at, clock, _PRE_UPDATE_MARGIN_SECONDS)
        post_error: FencedRollbackError | None = None
        try:
            receipt = _request_json(
                opener,
                token=token,
                method="POST",
                url=machine_url,
                expected_status=200,
                lease_nonce=lease_nonce,
                payload={
                    "config": previous_config,
                    "current_version": args.expected_instance,
                    "skip_launch": False,
                },
            )
            if (
                not isinstance(receipt, dict)
                or receipt.get("id") != args.machine_id
                or not isinstance(receipt.get("instance_id"), str)
            ):
                post_error = FencedRollbackError("Fly Machine rollback response was malformed")
        except FencedRollbackError as exc:
            # The request body may have reached Fly even if the response was
            # lost. Never retry the POST; a leased GET is the authority.
            post_error = exc

        _require_lease_margin(lease_expires_at, clock, _POST_UPDATE_MARGIN_SECONDS)
        try:
            _verify_restored_under_lease(
                opener=opener,
                token=token,
                machine_url=machine_url,
                machines_url=machines_url,
                lease_nonce=lease_nonce,
                lease_expires_at=lease_expires_at,
                args=args,
                expected_config=previous_config,
                clock=clock,
                sleeper=sleeper,
            )
        except FencedRollbackError as exc:
            if post_error is not None:
                raise FencedRollbackError(
                    "Fly Machine rollback outcome could not be reconciled"
                ) from exc
            raise

        _require_lease_margin(lease_expires_at, clock, _VERIFIED_RELEASE_MARGIN_SECONDS)
        update_verified = True
    finally:
        operation_failed = sys.exc_info()[0] is not None
        if lease_nonce is not None:
            try:
                _request_json(
                    opener,
                    token=token,
                    method="DELETE",
                    url=lease_url,
                    expected_status=200,
                    lease_nonce=lease_nonce,
                )
            except FencedRollbackError:
                if update_verified:
                    print(
                        "fenced rollback verified, but Machine lease release failed; wait for expiry",
                        file=sys.stderr,
                    )
                    raise
                elif operation_failed:
                    print(
                        "fenced rollback failed; bounded Machine lease release also failed",
                        file=sys.stderr,
                    )
                else:
                    raise


def _parser() -> argparse.ArgumentParser:
    parser = _SanitizedParser()
    parser.add_argument("--app", required=True)
    parser.add_argument("--machine-id", required=True)
    parser.add_argument("--expected-instance", required=True)
    parser.add_argument("--expected-image", required=True)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--expected-release", required=True)
    parser.add_argument("--expected-release-version", required=True)
    parser.add_argument("--expected-rollback-from-version", required=True)
    parser.add_argument("--expected-rollback-to-version", required=True)
    parser.add_argument("--expected-config-fingerprint", required=True)
    parser.add_argument("--baseline-machine-id", required=True)
    parser.add_argument("--baseline-instance", required=True)
    parser.add_argument("--baseline-image", required=True)
    parser.add_argument("--baseline-digest", required=True)
    parser.add_argument("--baseline-release", required=True)
    parser.add_argument("--baseline-release-version", required=True)
    parser.add_argument("--baseline-config-fingerprint", required=True)
    parser.add_argument("--allow-legacy-baseline-on-failure", action="store_true")
    parser.add_argument("--previous-status", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        fenced_rollback(_parser().parse_args(argv))
    except Exception as exc:  # noqa: BLE001 - never render API/token material
        kind = type(exc).__name__
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", kind) is None:
            kind = "Exception"
        print(f"fenced Fly rollback failed ({kind})", file=sys.stderr)
        return 1
    print("fenced Fly rollback verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
