"""Deterministic tests for the fenced Fly Machine rollback transaction."""

from __future__ import annotations

import argparse
import io
import json
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

from scripts import fenced_machine_rollback as fenced

_NOW = 1_700_000_000
_TOKEN = "sentinel-token-never-render"


def _clone(value):
    return json.loads(json.dumps(value))


class _Response:
    def __init__(
        self,
        url: str,
        status: int,
        payload: Any | None = None,
        *,
        raw: bytes | None = None,
    ):
        self._url = url
        self.status = status
        self._body = raw if raw is not None else json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self._url

    def read(self, _limit: int):
        return self._body


class _FlyAPI:
    def __init__(self, current: dict, *, scenario: str | None = None):
        self.current = _clone(current)
        self.scenario = scenario
        self.calls: list[dict[str, Any]] = []
        self.lease_nonce = "lease-nonce-123"
        self.now = float(_NOW)
        self.update_count = 0
        self.post_count = 0
        self.machine_get_count = 0
        self.list_get_count = 0
        self.sleep_calls: list[int] = []

    def _newer(self):
        self.current = _clone(self.current)
        self.current["instance_id"] = "instance-newer-037"
        self.current["config"]["image"] = "registry.fly.io/tradagent:newer"
        self.current["config"]["metadata"]["fly_release_id"] = "release-newer"
        self.current["config"]["metadata"]["fly_release_version"] = "37"
        self.current["image_ref"]["digest"] = "sha256:" + "3" * 64

    def _apply(self, body: dict):
        image = body["config"]["image"]
        pinned_digest = (
            image.rsplit("@", 1)[1]
            if "@" in image
            else "sha256:" + "1" * 64
        )
        self.update_count += 1
        self.current = {
            **self.current,
            "instance_id": "instance-rollback-038",
            "state": "started",
            "host_status": "ok",
            "incomplete_config": None,
            "image_ref": {**self.current["image_ref"], "digest": pinned_digest},
            "config": _clone(body["config"]),
        }

    def open(self, request, timeout):
        assert timeout == fenced._REQUEST_TIMEOUT_SECONDS
        method = request.get_method()
        url = request.full_url
        is_lease = url.endswith("/lease")
        is_collection = url.endswith("/machines")
        nonce = request.get_header("Fly-machine-lease-nonce")
        body = json.loads(request.data) if request.data else None
        if is_lease:
            kind = "lease-post" if method == "POST" else "lease-delete"
        elif is_collection:
            kind = "machines-get"
        elif method == "POST":
            kind = "machine-post"
        else:
            kind = "machine-get"
        self.calls.append({"kind": kind, "nonce": nonce, "body": body})

        if kind == "lease-post":
            assert nonce is None
            assert body == {
                "description": "tradingagents conditional rollback",
                "ttl": fenced._LEASE_SECONDS,
            }
            if self.scenario == "lease_conflict":
                raise HTTPError(url, 409, "private-conflict", {}, io.BytesIO())
            if self.scenario == "before_lease":
                self._newer()
            lease_seconds = fenced._LEASE_SECONDS
            if self.scenario == "short_lease":
                lease_seconds = fenced._MIN_LEASE_REMAINING_SECONDS - 1
            elif self.scenario == "long_lease":
                lease_seconds += fenced._LEASE_CLOCK_SKEW_SECONDS + 1
            return _Response(
                url,
                201,
                {
                    "status": "success",
                    "data": {
                        "nonce": self.lease_nonce,
                        "version": self.current["instance_id"],
                        "expires_at": int(self.now + lease_seconds),
                    },
                },
            )

        if kind == "lease-delete":
            assert nonce == self.lease_nonce
            if self.scenario == "release_failure":
                raise HTTPError(
                    "https://sentinel.invalid/private",
                    503,
                    "sentinel-release-secret",
                    {},
                    io.BytesIO(b"sentinel-release-body"),
                )
            return _Response(url, 200, {"status": "success", "data": {"ok": True}})

        if kind == "machines-get":
            assert nonce is None
            self.list_get_count += 1
            response = [_clone(self.current)]
            if self.scenario == "multiple_before" or (
                self.scenario == "multiple_after" and self.update_count
            ):
                extra = _clone(self.current)
                extra["id"] = "extra-machine-999"
                extra["instance_id"] = "instance-extra-999"
                response.append(extra)
            if self.scenario == "margin_before_update" and self.update_count == 0:
                self.now += fenced._LEASE_SECONDS - fenced._PRE_UPDATE_MARGIN_SECONDS + 1
            return _Response(url, 200, response)

        assert nonce == self.lease_nonce
        if kind == "machine-get":
            self.machine_get_count += 1
            response = _clone(self.current)
            if (
                self.scenario == "applied_transitional"
                and self.update_count
                and self.current["state"] == "starting"
            ):
                self.current["state"] = "started"
            return _Response(url, 200, response)

        assert kind == "machine-post"
        self.post_count += 1
        assert body["current_version"] == "instance-target-036"
        assert body["config"]["image"] == (
            "registry.fly.io/tradagent:"
            "deployment-01KZAD8T2KXJJJXAM2JJW8E447"
        ) or body["config"]["image"].endswith("@sha256:" + "1" * 64)
        if self.scenario == "race_before_update":
            self._newer()
        if body["current_version"] != self.current["instance_id"]:
            raise HTTPError(url, 409, "private-conflict", {}, io.BytesIO())
        if self.scenario == "not_applied_timeout":
            raise TimeoutError("sentinel-timeout-secret")
        if self.scenario == "not_applied_http_error":
            raise HTTPError(
                "https://sentinel.invalid/private",
                502,
                "sentinel-api-secret",
                {},
                io.BytesIO(b"sentinel-api-body"),
            )

        self._apply(body)
        if self.scenario == "applied_transitional":
            self.current["state"] = "starting"
        if self.scenario == "wrong_digest_after":
            self.current["image_ref"]["digest"] = "sha256:" + "9" * 64
        if self.scenario == "wrong_config_after":
            self.current["config"]["env"]["MEDIA_HEALTH_PORT"] = "9999"
        if self.scenario == "bad_host_after":
            self.current["host_status"] = "unreachable"
        if self.scenario == "applied_timeout":
            raise TimeoutError("sentinel-timeout-secret")
        if self.scenario == "applied_http_error":
            raise HTTPError(
                "https://sentinel.invalid/private",
                502,
                "sentinel-api-secret",
                {},
                io.BytesIO(b"sentinel-api-body"),
            )
        if self.scenario == "applied_malformed":
            return _Response(url, 200, raw=b"{sentinel-malformed-response")
        if self.scenario == "applied_bad_receipt":
            return _Response(url, 200, [])
        return _Response(url, 200, _clone(self.current))


@pytest.fixture
def rollback_case(tmp_path, monkeypatch):
    target = {
        "id": "891e16dce79598",
        "instance_id": "instance-target-036",
        "state": "started",
        "host_status": "ok",
        "incomplete_config": None,
        "image_ref": {"digest": "sha256:" + "2" * 64},
        "config": {
            "image": "registry.fly.io/tradagent:target",
            "metadata": {
                "fly_process_group": "app",
                "fly_release_id": "release-target",
                "fly_release_version": "36",
            },
            "env": {"FLY_PROCESS_GROUP": "app", "MEDIA_HEALTH_PORT": "5500"},
            "guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 256},
            "init": {},
            "restart": {"policy": "always"},
        },
    }
    baseline = {
        "id": "891e16dce79598",
        "instance_id": "instance-baseline-033",
        "state": "started",
        "host_status": "ok",
        "incomplete_config": None,
        "image_ref": {"digest": "sha256:" + "1" * 64},
        "config": {
            "image": (
                "registry.fly.io/tradagent:"
                "deployment-01KZAD8T2KXJJJXAM2JJW8E447"
            ),
            "metadata": {
                "fly_process_group": "app",
                "fly_release_id": "release-baseline",
                "fly_release_version": "33",
                "collector_owner": "tradingagents",
            },
            "env": {"FLY_PROCESS_GROUP": "app", "MEDIA_HEALTH_PORT": "5500"},
            "guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 256},
            "init": {},
            "restart": {"policy": "always"},
        },
    }
    status_path = tmp_path / "previous.json"
    status_path.write_text(json.dumps({"Machines": [baseline]}), encoding="utf-8")
    args = argparse.Namespace(
        app="tradagent",
        machine_id=target["id"],
        expected_instance=target["instance_id"],
        expected_image=target["config"]["image"],
        expected_digest=target["image_ref"]["digest"],
        expected_release="release-target",
        expected_release_version="36",
        expected_rollback_from_version="0",
        expected_rollback_to_version="0",
        expected_config_fingerprint=fenced._config_fingerprint(target["config"]),
        baseline_machine_id=baseline["id"],
        baseline_instance=baseline["instance_id"],
        baseline_image=baseline["config"]["image"],
        baseline_digest=baseline["image_ref"]["digest"],
        baseline_release="release-baseline",
        baseline_release_version="33",
        baseline_config_fingerprint=fenced._config_fingerprint(baseline["config"]),
        allow_legacy_baseline_on_failure=False,
        previous_status=str(status_path),
    )
    monkeypatch.setenv("FLY_API_TOKEN", _TOKEN)
    return args, target, baseline


def _run(args, api):
    def sleep(seconds):
        api.sleep_calls.append(seconds)
        api.now += seconds

    fenced.fenced_rollback(
        args,
        opener=api,
        clock=lambda: api.now,
        sleeper=sleep,
    )


def _rewrite_status(args, machines):
    Path(args.previous_status).write_text(json.dumps({"Machines": machines}), encoding="utf-8")


def _argv(args):
    argv = [
        "--app",
        args.app,
        "--machine-id",
        args.machine_id,
        "--expected-instance",
        args.expected_instance,
        "--expected-image",
        args.expected_image,
        "--expected-digest",
        args.expected_digest,
        "--expected-release",
        args.expected_release,
        "--expected-release-version",
        args.expected_release_version,
        "--expected-rollback-from-version",
        args.expected_rollback_from_version,
        "--expected-rollback-to-version",
        args.expected_rollback_to_version,
        "--expected-config-fingerprint",
        args.expected_config_fingerprint,
        "--baseline-machine-id",
        args.baseline_machine_id,
        "--baseline-instance",
        args.baseline_instance,
        "--baseline-image",
        args.baseline_image,
        "--baseline-digest",
        args.baseline_digest,
        "--baseline-release",
        args.baseline_release,
        "--baseline-release-version",
        args.baseline_release_version,
        "--baseline-config-fingerprint",
        args.baseline_config_fingerprint,
        "--previous-status",
        args.previous_status,
    ]
    if args.allow_legacy_baseline_on_failure:
        argv.append("--allow-legacy-baseline-on-failure")
    return argv


@pytest.mark.unit
def test_exact_digest_pinned_rollback_is_verified_before_release(rollback_case):
    args, target, baseline = rollback_case
    api = _FlyAPI(target)

    _run(args, api)

    assert [call["kind"] for call in api.calls] == [
        "lease-post",
        "machine-get",
        "machines-get",
        "machine-post",
        "machine-get",
        "machines-get",
        "lease-delete",
    ]
    assert api.post_count == api.update_count == 1
    assert all(
        call["nonce"] == api.lease_nonce
        for call in api.calls
        if call["kind"] in {"machine-get", "machine-post", "lease-delete"}
    )
    update = next(call["body"] for call in api.calls if call["kind"] == "machine-post")
    assert update["current_version"] == target["instance_id"]
    assert update["config"]["image"] == (
        baseline["config"]["image"] + "@" + baseline["image_ref"]["digest"]
    )
    assert api.current["image_ref"]["digest"] == baseline["image_ref"]["digest"]
    assert api.current["config"] == update["config"]

    metadata = update["config"]["metadata"]
    expected_lineage = {
        fenced._ROLLBACK_SCHEMA: "1",
        fenced._ROLLBACK_RECORDED_AT: "2023-11-14T22:13:20Z",
        fenced._ROLLBACK_FROM: "36",
        fenced._ROLLBACK_TO: "33",
        fenced._ROLLBACK_FROM_MACHINE: target["id"],
        fenced._ROLLBACK_FROM_INSTANCE: target["instance_id"],
        fenced._ROLLBACK_FROM_RELEASE: "release-target",
        fenced._ROLLBACK_FROM_DIGEST: target["image_ref"]["digest"],
        fenced._ROLLBACK_FROM_CONFIG: args.expected_config_fingerprint,
        fenced._ROLLBACK_TO_MACHINE: baseline["id"],
        fenced._ROLLBACK_TO_INSTANCE: baseline["instance_id"],
        fenced._ROLLBACK_TO_RELEASE: "release-baseline",
        fenced._ROLLBACK_TO_DIGEST: baseline["image_ref"]["digest"],
        fenced._ROLLBACK_TO_CONFIG: args.baseline_config_fingerprint,
        fenced._ROLLBACK_PARENT: "0" * 64,
        fenced._ROLLBACK_IMAGE_MODE: "digest-pinned",
    }
    for key, value in expected_lineage.items():
        assert metadata[key] == value
    assert re.fullmatch(r"[0-9a-f]{64}", metadata[fenced._ROLLBACK_OPERATION])
    assert re.fullmatch(r"[0-9a-f]{64}", metadata[fenced._ROLLBACK_BASELINE_STATUS])
    assert metadata["collector_owner"] == "tradingagents"
    assert api.calls[-1]["kind"] == "lease-delete"


@pytest.mark.unit
@pytest.mark.parametrize(
    "scenario",
    [
        "applied_timeout",
        "applied_http_error",
        "applied_malformed",
        "applied_bad_receipt",
    ],
)
def test_ambiguous_applied_post_is_reconciled_without_retry(rollback_case, scenario):
    args, target, _baseline = rollback_case
    api = _FlyAPI(target, scenario=scenario)

    _run(args, api)

    assert api.post_count == api.update_count == 1
    assert api.machine_get_count == 2
    assert api.list_get_count == 2
    assert api.calls[-1]["kind"] == "lease-delete"
    assert api.current["instance_id"] == "instance-rollback-038"


@pytest.mark.unit
def test_transitional_post_state_is_polled_read_only_until_exact(rollback_case):
    args, target, _baseline = rollback_case
    api = _FlyAPI(target, scenario="applied_transitional")

    _run(args, api)

    assert api.post_count == api.update_count == 1
    assert api.machine_get_count == 3
    assert api.list_get_count == 2
    assert api.sleep_calls == [fenced._VERIFY_INTERVAL_SECONDS]
    assert api.current["state"] == "started"
    assert api.calls[-1]["kind"] == "lease-delete"


@pytest.mark.unit
@pytest.mark.parametrize("scenario", ["not_applied_timeout", "not_applied_http_error"])
def test_ambiguous_unapplied_post_fails_closed_without_retry(rollback_case, scenario):
    args, target, _baseline = rollback_case
    api = _FlyAPI(target, scenario=scenario)

    with pytest.raises(fenced.FencedRollbackError):
        _run(args, api)

    assert api.post_count == 1
    assert api.update_count == 0
    assert api.machine_get_count == 1 + fenced._VERIFY_ATTEMPTS
    assert api.list_get_count == 1
    assert api.sleep_calls == [fenced._VERIFY_INTERVAL_SECONDS] * (fenced._VERIFY_ATTEMPTS - 1)
    assert api.current["instance_id"] == target["instance_id"]
    assert api.calls[-1]["kind"] == "lease-delete"


@pytest.mark.unit
def test_current_version_blocks_change_after_leased_preflight(rollback_case):
    args, target, _baseline = rollback_case
    api = _FlyAPI(target, scenario="race_before_update")

    with pytest.raises(fenced.FencedRollbackError):
        _run(args, api)

    assert api.post_count == 1
    assert api.update_count == 0
    assert api.current["instance_id"] == "instance-newer-037"
    assert [call["kind"] for call in api.calls].count("machine-post") == 1
    assert api.calls[-1]["kind"] == "lease-delete"


@pytest.mark.unit
@pytest.mark.parametrize(
    "defect",
    [
        "host_missing",
        "host_unreachable",
        "incomplete_config",
        "missing_config",
        "missing_init",
        "wrong_env_type",
        "mounted_volume",
        "injected_file",
        "wrong_restart",
        "wrong_process_group",
        "extra_machine",
        "machine_mismatch",
        "instance_mismatch",
        "image_mismatch",
        "digest_mismatch",
        "release_mismatch",
        "release_version_mismatch",
        "semantic_config_mismatch",
    ],
)
def test_invalid_or_stateful_baseline_is_rejected_before_lease(rollback_case, defect):
    args, target, baseline = rollback_case
    baseline = _clone(baseline)
    machines = [baseline]
    if defect == "host_missing":
        baseline.pop("host_status")
    elif defect == "host_unreachable":
        baseline["host_status"] = "unreachable"
    elif defect == "incomplete_config":
        baseline["incomplete_config"] = {"image": baseline["config"]["image"]}
    elif defect == "missing_config":
        baseline["config"] = None
    elif defect == "missing_init":
        baseline["config"].pop("init")
    elif defect == "wrong_env_type":
        baseline["config"]["env"] = []
    elif defect == "mounted_volume":
        baseline["config"]["mounts"] = [{"volume": "private-volume"}]
    elif defect == "injected_file":
        baseline["config"]["files"] = [{"guest_path": "/private"}]
    elif defect == "wrong_restart":
        baseline["config"]["restart"] = {
            "policy": "on-failure",
            "max_retries": 10,
        }
    elif defect == "wrong_process_group":
        baseline["config"]["metadata"]["fly_process_group"] = "worker"
        baseline["config"]["env"]["FLY_PROCESS_GROUP"] = "worker"
    elif defect == "extra_machine":
        machines.append({**_clone(baseline), "id": "extra-machine-999"})
    elif defect == "machine_mismatch":
        baseline["id"] = "different-machine-999"
    elif defect == "instance_mismatch":
        baseline["instance_id"] = "different-instance-999"
    elif defect == "image_mismatch":
        baseline["config"]["image"] = "registry.fly.io/tradagent:different"
    elif defect == "digest_mismatch":
        baseline["image_ref"]["digest"] = "sha256:" + "8" * 64
    elif defect == "release_mismatch":
        baseline["config"]["metadata"]["fly_release_id"] = "release-different"
    elif defect == "release_version_mismatch":
        baseline["config"]["metadata"]["fly_release_version"] = "32"
    elif defect == "semantic_config_mismatch":
        baseline["config"]["guest"]["memory_mb"] = 512
    _rewrite_status(args, machines)
    api = _FlyAPI(target)

    with pytest.raises(fenced.FencedRollbackError):
        _run(args, api)

    assert api.calls == []
    assert api.post_count == api.update_count == 0


@pytest.mark.unit
def test_explicit_legacy_flag_allows_only_authenticated_on_failure_baseline(
    rollback_case,
):
    args, target, baseline = rollback_case
    baseline = _clone(baseline)
    baseline["config"]["restart"] = {
        "policy": "on-failure",
        "max_retries": 10,
    }
    baseline["config"]["env"].pop("MEDIA_HEALTH_PORT")
    args.baseline_config_fingerprint = fenced._config_fingerprint(baseline["config"])
    args.allow_legacy_baseline_on_failure = True
    _rewrite_status(args, [baseline])
    api = _FlyAPI(target)

    _run(args, api)

    update = next(call["body"] for call in api.calls if call["kind"] == "machine-post")
    assert update["config"]["image"] == baseline["config"]["image"]
    assert update["config"]["restart"] == {
        "policy": "on-failure",
        "max_retries": 10,
    }
    assert update["config"]["metadata"][fenced._ROLLBACK_IMAGE_MODE] == (
        "legacy-bare-deployment-tag"
    )
    assert api.current["config"]["restart"] == update["config"]["restart"]


@pytest.mark.unit
def test_legacy_flag_keeps_health_enabled_deployment_image_digest_pinned(
    rollback_case,
):
    args, target, baseline = rollback_case
    args.allow_legacy_baseline_on_failure = True
    api = _FlyAPI(target)

    _run(args, api)

    update = next(call["body"] for call in api.calls if call["kind"] == "machine-post")
    assert update["config"]["image"] == (
        baseline["config"]["image"] + "@" + baseline["image_ref"]["digest"]
    )
    assert update["config"]["metadata"][fenced._ROLLBACK_IMAGE_MODE] == (
        "digest-pinned"
    )


@pytest.mark.unit
def test_legacy_flag_does_not_unpin_non_deployment_image(rollback_case):
    args, target, baseline = rollback_case
    baseline = _clone(baseline)
    baseline["config"]["image"] = (
        "registry.fly.io/tradagent:git-" + "a" * 40 + "-" + "b" * 32
    )
    baseline["config"]["restart"] = {
        "policy": "on-failure",
        "max_retries": 10,
    }
    baseline["config"]["env"].pop("MEDIA_HEALTH_PORT")
    args.baseline_image = baseline["config"]["image"]
    args.baseline_config_fingerprint = fenced._config_fingerprint(baseline["config"])
    args.allow_legacy_baseline_on_failure = True
    _rewrite_status(args, [baseline])
    api = _FlyAPI(target)

    _run(args, api)

    update = next(call["body"] for call in api.calls if call["kind"] == "machine-post")
    assert update["config"]["image"] == (
        baseline["config"]["image"] + "@" + baseline["image_ref"]["digest"]
    )
    assert update["config"]["metadata"][fenced._ROLLBACK_IMAGE_MODE] == (
        "digest-pinned"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "restart",
    [
        {"policy": "on-failure"},
        {"policy": "on-failure", "max_retries": 0},
        {"policy": "on-failure", "max_retries": 101},
        {"policy": "never", "max_retries": 10},
    ],
)
def test_legacy_flag_does_not_broaden_other_baseline_restart_policies(rollback_case, restart):
    args, target, baseline = rollback_case
    baseline = _clone(baseline)
    baseline["config"]["restart"] = restart
    args.baseline_config_fingerprint = fenced._config_fingerprint(baseline["config"])
    args.allow_legacy_baseline_on_failure = True
    _rewrite_status(args, [baseline])
    api = _FlyAPI(target)

    with pytest.raises(fenced.FencedRollbackError):
        _run(args, api)

    assert api.calls == []


@pytest.mark.unit
def test_legacy_baseline_flag_never_weakens_candidate_restart_policy(rollback_case):
    args, target, _baseline = rollback_case
    target = _clone(target)
    target["config"]["restart"] = {
        "policy": "on-failure",
        "max_retries": 10,
    }
    args.expected_config_fingerprint = fenced._config_fingerprint(target["config"])
    args.allow_legacy_baseline_on_failure = True
    api = _FlyAPI(target)

    with pytest.raises(fenced.OwnershipChanged):
        _run(args, api)

    assert api.post_count == api.update_count == 0
    assert api.calls[-1]["kind"] == "lease-delete"


@pytest.mark.unit
@pytest.mark.parametrize(
    "defect",
    [
        "host_missing",
        "host_unreachable",
        "incomplete_config",
        "missing_config",
        "wrong_env_type",
        "mounted_volume",
        "injected_file",
        "wrong_restart",
        "wrong_process_group",
        "extra_machine",
    ],
)
def test_invalid_current_machine_or_topology_never_updates(rollback_case, defect):
    args, target, _baseline = rollback_case
    target = _clone(target)
    scenario = None
    if defect == "host_missing":
        target.pop("host_status")
    elif defect == "host_unreachable":
        target["host_status"] = "unreachable"
    elif defect == "incomplete_config":
        target["incomplete_config"] = {"image": target["config"]["image"]}
    elif defect == "missing_config":
        target["config"] = None
    elif defect == "wrong_env_type":
        target["config"]["env"] = []
    elif defect == "mounted_volume":
        target["config"]["mounts"] = [{"volume": "private-volume"}]
    elif defect == "injected_file":
        target["config"]["files"] = [{"guest_path": "/private"}]
    elif defect == "wrong_restart":
        target["config"]["restart"] = {
            "policy": "on-failure",
            "max_retries": 10,
        }
    elif defect == "wrong_process_group":
        target["config"]["metadata"]["fly_process_group"] = "worker"
        target["config"]["env"]["FLY_PROCESS_GROUP"] = "worker"
    elif defect == "extra_machine":
        scenario = "multiple_before"
    api = _FlyAPI(target, scenario=scenario)

    with pytest.raises(fenced.FencedRollbackError):
        _run(args, api)

    assert api.post_count == api.update_count == 0
    assert api.calls[-1]["kind"] == "lease-delete"


@pytest.mark.unit
@pytest.mark.parametrize(
    "scenario",
    [
        "wrong_digest_after",
        "wrong_config_after",
        "bad_host_after",
        "multiple_after",
    ],
)
def test_post_update_exact_digest_and_topology_are_required(rollback_case, scenario):
    args, target, _baseline = rollback_case
    api = _FlyAPI(target, scenario=scenario)

    with pytest.raises(fenced.FencedRollbackError):
        _run(args, api)

    assert api.post_count == api.update_count == 1
    assert api.calls[-1]["kind"] == "lease-delete"


@pytest.mark.unit
@pytest.mark.parametrize("scenario", ["short_lease", "long_lease"])
def test_unexpected_lease_bounds_fail_before_machine_reads(rollback_case, scenario):
    args, target, _baseline = rollback_case
    api = _FlyAPI(target, scenario=scenario)

    with pytest.raises(fenced.FencedRollbackError):
        _run(args, api)

    assert [call["kind"] for call in api.calls] == ["lease-post", "lease-delete"]
    assert api.post_count == api.update_count == 0


@pytest.mark.unit
def test_lease_margin_is_rechecked_before_the_only_update(rollback_case):
    args, target, _baseline = rollback_case
    api = _FlyAPI(target, scenario="margin_before_update")

    with pytest.raises(fenced.FencedRollbackError):
        _run(args, api)

    assert api.post_count == api.update_count == 0
    assert [call["kind"] for call in api.calls] == [
        "lease-post",
        "machine-get",
        "machines-get",
        "lease-delete",
    ]


@pytest.mark.unit
def test_lease_expiry_margin_stops_reconciliation_without_retry(rollback_case):
    args, target, _baseline = rollback_case
    api = _FlyAPI(target, scenario="not_applied_timeout")

    def expire_during_reconciliation(_seconds):
        api.now = (
            _NOW
            + fenced._LEASE_SECONDS
            - fenced._REQUEST_TIMEOUT_SECONDS
            - fenced._VERIFIED_RELEASE_MARGIN_SECONDS
            + 1
        )

    with pytest.raises(fenced.FencedRollbackError):
        fenced.fenced_rollback(
            args,
            opener=api,
            clock=lambda: api.now,
            sleeper=expire_during_reconciliation,
        )

    assert api.post_count == 1
    assert api.update_count == 0
    assert api.machine_get_count == 2
    assert api.calls[-1]["kind"] == "lease-delete"


@pytest.mark.unit
def test_newer_instance_before_lease_and_lease_conflict_never_update(rollback_case):
    args, target, _baseline = rollback_case
    before_lease = _FlyAPI(target, scenario="before_lease")
    with pytest.raises(fenced.OwnershipChanged):
        _run(args, before_lease)
    assert [call["kind"] for call in before_lease.calls] == [
        "lease-post",
        "lease-delete",
    ]
    assert before_lease.post_count == 0

    conflict = _FlyAPI(target, scenario="lease_conflict")
    with pytest.raises(fenced.FencedRollbackError):
        _run(args, conflict)
    assert [call["kind"] for call in conflict.calls] == ["lease-post"]
    assert conflict.post_count == 0


@pytest.mark.unit
def test_prior_lineage_is_chained_and_unrelated_metadata_is_preserved(rollback_case):
    args, target, baseline = rollback_case
    baseline = _clone(baseline)
    prior = {
        fenced._ROLLBACK_SCHEMA: "1",
        fenced._ROLLBACK_OPERATION: "a" * 64,
        fenced._ROLLBACK_FROM: "32",
        fenced._ROLLBACK_TO: "31",
    }
    baseline["config"]["metadata"].update(prior)
    _rewrite_status(args, [baseline])
    api = _FlyAPI(target)

    _run(args, api)

    update = next(call["body"] for call in api.calls if call["kind"] == "machine-post")
    metadata = update["config"]["metadata"]
    assert metadata[fenced._ROLLBACK_PARENT] == fenced._sha256_json(prior)
    assert metadata[fenced._ROLLBACK_FROM] == "36"
    assert metadata[fenced._ROLLBACK_TO] == "33"
    assert metadata["collector_owner"] == "tradingagents"


@pytest.mark.unit
def test_verified_update_with_release_failure_is_nonzero_and_sanitized(rollback_case, capsys):
    args, target, _baseline = rollback_case
    api = _FlyAPI(target, scenario="release_failure")

    with pytest.raises(fenced.FencedRollbackError):
        _run(args, api)

    rendered = capsys.readouterr()
    assert rendered.out == ""
    assert rendered.err == (
        "fenced rollback verified, but Machine lease release failed; wait for expiry\n"
    )
    assert "sentinel" not in rendered.err
    assert api.post_count == api.update_count == 1


@pytest.mark.unit
def test_release_failure_returns_nonzero_from_process_boundary(rollback_case, monkeypatch, capsys):
    args, target, _baseline = rollback_case
    api = _FlyAPI(target, scenario="release_failure")
    monkeypatch.setattr(fenced, "build_opener", lambda *_args: api)
    monkeypatch.setattr(fenced.time, "time", lambda: api.now)

    result = fenced.main(_argv(args))

    rendered = capsys.readouterr()
    assert result == 1
    assert rendered.out == ""
    assert rendered.err == (
        "fenced rollback verified, but Machine lease release failed; wait for expiry\n"
        "fenced Fly rollback failed (FencedRollbackError)\n"
    )
    assert "sentinel" not in rendered.err
    assert api.post_count == api.update_count == 1


@pytest.mark.unit
def test_real_main_boundary_sanitizes_transport_and_argument_secrets(
    rollback_case, monkeypatch, capsys
):
    args, target, _baseline = rollback_case
    api = _FlyAPI(target, scenario="not_applied_http_error")
    monkeypatch.setattr(fenced, "build_opener", lambda *_args: api)
    monkeypatch.setattr(fenced.time, "time", lambda: api.now)
    monkeypatch.setattr(fenced.time, "sleep", lambda _seconds: None)

    result = fenced.main(_argv(args))
    rendered = capsys.readouterr()
    assert result == 1
    assert rendered.out == ""
    assert rendered.err == "fenced Fly rollback failed (FencedRollbackError)\n"
    combined = rendered.out + rendered.err
    assert _TOKEN not in combined
    assert "sentinel-api" not in combined
    assert args.previous_status not in combined
    assert "api.machines.dev" not in combined

    result = fenced.main([*_argv(args), "--sentinel-private-argument"])
    rendered = capsys.readouterr()
    assert result == 1
    assert rendered.out == ""
    assert rendered.err == "fenced Fly rollback failed (FencedRollbackError)\n"
    assert "sentinel-private-argument" not in rendered.err
