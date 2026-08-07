"""Behavioral tests for the collector's transactional Fly deploy wrapper."""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "scripts" / "deploy_collector.sh"
REVISION = "a" * 40
PREVIOUS_IMAGE = "registry.fly.io/tradagent:deployment-previous"


FAKE_GIT = r"""#!/usr/bin/env python3
import json
import os
import pathlib
import sys

state_dir = pathlib.Path(os.environ["FAKE_STATE_DIR"])
args = sys.argv[1:]
with (state_dir / "git-calls.jsonl").open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\n")

if args == ["status", "--porcelain"]:
    raise SystemExit(0)
if args == ["rev-parse", "--verify", "HEAD"]:
    print(os.environ["FAKE_REVISION"])
    raise SystemExit(0)
if args[:2] == ["rev-parse", "--verify"]:
    print(os.environ.get("FAKE_LOCAL_TARGET_REVISION", os.environ["FAKE_REVISION"]))
    raise SystemExit(0)
if args and args[0] == "check-ref-format":
    raise SystemExit(1 if os.environ.get("FAKE_INVALID_TARGET") == "true" else 0)
if args[:3] == ["ls-remote", "--exit-code", "--refs"]:
    count_path = state_dir / "ls-remote-count"
    count = int(count_path.read_text()) if count_path.exists() else 0
    count_path.write_text(str(count + 1))
    mode = (
        os.environ.get("FAKE_REMOTE_MODE_AFTER", "")
        if count > 0
        else os.environ.get("FAKE_REMOTE_MODE", "")
    )
    if mode == "unavailable":
        print(
            "fatal: could not read https://user:remote-secret@example.invalid/repo.git",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if mode == "malformed":
        print("not-a-revision\trefs/heads/main")
        raise SystemExit(0)
    revision = (
        os.environ.get("FAKE_REMOTE_REVISION_AFTER", "")
        if count > 0
        else os.environ.get("FAKE_REMOTE_REVISION", "")
    ) or os.environ["FAKE_REVISION"]
    print(f"{revision}\t{args[-1]}")
    raise SystemExit(0)

print("unexpected fake git invocation", args, file=sys.stderr)
raise SystemExit(2)
"""


FAKE_FLY = r'''#!/usr/bin/env python3
import json
import os
import pathlib
import signal
import sys

state_dir = pathlib.Path(os.environ["FAKE_STATE_DIR"])
scenario = os.environ.get("FAKE_SCENARIO", "success")
revision = os.environ["FAKE_REVISION"]
args = sys.argv[1:]
with (state_dir / "calls.jsonl").open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\n")

phase_path = state_dir / "phase"
phase = phase_path.read_text() if phase_path.exists() else "previous"

def value(flag):
    return args[args.index(flag) + 1]

def machine(kind):
    if kind == "previous":
        machine_id = "machine-old"
        image = "registry.fly.io/tradagent:deployment-previous"
        digest = "sha256:" + "1" * 64
        release = "release-old"
        env = {
            "FLY_PROCESS_GROUP": "app",
            "MEDIA_AUTO_MIGRATE": "false",
            "MEDIA_COLLECTION_ENABLED": "true",
        }
        restart = {"policy": "on-failure", "max_retries": 10}
    elif kind == "target":
        machine_id = "machine-new"
        image = f"registry.fly.io/tradagent:git-{revision}"
        digest = "sha256:" + "2" * 64
        release = "release-new"
        env = {
            "FLY_PROCESS_GROUP": "app",
            "MEDIA_AUTO_MIGRATE": "false",
            "MEDIA_COLLECTION_ENABLED": "true",
            "MEDIA_HEALTH_PORT": "5500",
        }
        restart = {"policy": "always"}
    else:
        machine_id = "machine-foreign"
        image = "registry.fly.io/tradagent:git-" + "b" * 40
        digest = "sha256:" + "3" * 64
        release = "release-foreign"
        env = {"FLY_PROCESS_GROUP": "app", "MEDIA_HEALTH_PORT": "5500"}
        restart = {"policy": "always"}
    return {
        "id": machine_id,
        "state": "started",
        "image_ref": {"digest": digest},
        "config": {
            "image": image,
            "metadata": {
                "fly_process_group": "app",
                "fly_release_id": release,
            },
            "env": env,
            "init": {"cmd": ["--global-only"]},
            "guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 256},
            "restart": restart,
        },
    }

if args[:2] == ["config", "validate"]:
    raise SystemExit(0)
if args[:2] == ["config", "save"]:
    pathlib.Path(value("-c")).write_text(
        "app = 'tradagent'\n[processes]\n  app = '--global-only'\n",
        encoding="utf-8",
    )
    raise SystemExit(0)
if args and args[0] == "status":
    if scenario == "superseded" and phase == "target":
        counter_path = state_dir / "target-status-count"
        count = int(counter_path.read_text()) if counter_path.exists() else 0
        counter_path.write_text(str(count + 1))
        # The first status identifies our target; the next proves a newer release.
        kind = "target" if count == 0 else "foreign"
    else:
        kind = phase
    print(json.dumps({"Machines": [machine(kind)]}))
    raise SystemExit(0)
if args and args[0] == "deploy":
    rollback = "--image" in args
    if rollback:
        if scenario == "rollback_failure":
            raise SystemExit(1)
        phase_path.write_text("previous")
        raise SystemExit(0)
    if scenario == "deploy_failure_unchanged":
        raise SystemExit(1)
    phase_path.write_text("target")
    if scenario == "deploy_failure_changed":
        raise SystemExit(1)
    raise SystemExit(0)
if args[:2] == ["checks", "list"]:
    if scenario in {"health_timeout", "wrong_machine_check"}:
        machine_id = "not-the-target" if scenario == "wrong_machine_check" else "machine-new"
        status = "passing" if scenario == "wrong_machine_check" else "critical"
    else:
        machine_id = "machine-new"
        status = "passing"
    print(json.dumps({
        machine_id: [{"name": "collector_health", "status": status}]
    }))
    raise SystemExit(0)
if args[:2] == ["ssh", "console"]:
    command = value("-C")
    if scenario == "signal" and "/opt/tradingagents/REVISION" in command:
        os.kill(os.getppid(), signal.SIGTERM)
        raise SystemExit(143)
    if scenario == "revision_mismatch" and "/opt/tradingagents/REVISION" in command:
        raise SystemExit(1)
    if scenario == "alert_failure" and "--test-alert" in command:
        raise SystemExit(1)
    raise SystemExit(0)

print("unexpected fake fly invocation", args, file=sys.stderr)
raise SystemExit(2)
'''


@pytest.fixture
def fake_deploy_env(tmp_path):
    bin_dir = tmp_path / "bin"
    state_dir = tmp_path / "state"
    bin_dir.mkdir()
    state_dir.mkdir()
    for name, body in (("git", FAKE_GIT), ("fly", FAKE_FLY)):
        executable = bin_dir / name
        executable.write_text(textwrap.dedent(body), encoding="utf-8")
        executable.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "TMPDIR": str(tmp_path),
        "FAKE_STATE_DIR": str(state_dir),
        "FAKE_REVISION": REVISION,
        "COLLECTOR_HEALTH_TIMEOUT_SECONDS": "1",
        "COLLECTOR_HEALTH_POLL_SECONDS": "1",
        "COLLECTOR_ROLLBACK_TIMEOUT_SECONDS": "1",
    }
    return env, state_dir


def _run(env, *, app="tradagent"):
    return subprocess.run(
        [str(DEPLOY), app],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _calls(state_dir):
    path = state_dir / "calls.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _git_calls(state_dir):
    return [
        json.loads(line)
        for line in (state_dir / "git-calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def _deploy_calls(state_dir):
    return [call for call in _calls(state_dir) if call and call[0] == "deploy"]


@pytest.mark.unit
def test_success_is_bound_to_target_machine_check_and_exact_revision(fake_deploy_env):
    env, state_dir = fake_deploy_env

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert f"healthy at {REVISION} on Machine machine-new" in result.stdout
    deploys = _deploy_calls(state_dir)
    assert len(deploys) == 1
    assert ["--build-arg", f"GIT_REVISION={REVISION}"] == deploys[0][
        deploys[0].index("--build-arg"):deploys[0].index("--build-arg") + 2
    ]
    assert ["--image-label", f"git-{REVISION}"] == deploys[0][
        deploys[0].index("--image-label"):deploys[0].index("--image-label") + 2
    ]
    ssh_call = next(call for call in _calls(state_dir) if call[:2] == ["ssh", "console"])
    assert ssh_call[ssh_call.index("--machine") + 1] == "machine-new"
    assert REVISION in ssh_call[ssh_call.index("-C") + 1]
    remote_reads = [call for call in _git_calls(state_dir) if call[:1] == ["ls-remote"]]
    assert remote_reads == [
        ["ls-remote", "--exit-code", "--refs", "origin", "refs/heads/main"],
        ["ls-remote", "--exit-code", "--refs", "origin", "refs/heads/main"],
    ]


@pytest.mark.unit
def test_primary_deploy_failure_restores_saved_legacy_config_and_image(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "deploy_failure_changed"

    result = _run(env)

    assert result.returncode == 1
    assert "deployment command failed" in result.stderr
    assert "previous collector image and configuration restored" in result.stdout
    deploys = _deploy_calls(state_dir)
    assert len(deploys) == 2
    rollback = deploys[1]
    assert rollback[rollback.index("--image") + 1] == PREVIOUS_IMAGE
    assert "--skip-release-command" in rollback
    assert rollback[rollback.index("-c") + 1].endswith("fly.previous.toml")
    assert rollback[rollback.index("--strategy") + 1] == "immediate"


@pytest.mark.unit
def test_pre_mutation_deploy_failure_leaves_known_good_release_alone(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "deploy_failure_unchanged"

    result = _run(env)

    assert result.returncode == 1
    assert len(_deploy_calls(state_dir)) == 1
    assert "previous collector image and configuration remain active" in result.stderr


@pytest.mark.unit
@pytest.mark.parametrize("scenario", ["health_timeout", "wrong_machine_check", "revision_mismatch"])
def test_unverified_target_rolls_back(scenario, fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario

    result = _run(env)

    assert result.returncode == 1
    assert len(_deploy_calls(state_dir)) == 2
    assert "previous collector image and configuration restored" in result.stdout


@pytest.mark.unit
def test_superseding_release_is_never_rolled_back(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "superseded"

    result = _run(env)

    assert result.returncode == 75
    assert len(_deploy_calls(state_dir)) == 1
    assert "superseded" in result.stderr
    assert "refusing to roll back a newer release" in result.stderr


@pytest.mark.unit
def test_alert_failure_preserves_revision_verified_release(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "alert_failure"

    result = _run(env)

    assert result.returncode == 1
    assert len(_deploy_calls(state_dir)) == 1
    assert "alert was not delivered" in result.stderr
    assert "not rolling back code" in result.stderr


@pytest.mark.unit
def test_signal_after_remote_mutation_runs_controlled_rollback(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "signal"

    result = _run(env)

    assert result.returncode == 143
    assert len(_deploy_calls(state_dir)) == 2
    assert "interrupted by TERM" in result.stderr
    assert "previous collector image and configuration restored" in result.stdout


@pytest.mark.unit
def test_deploy_target_must_match_checked_in_app(fake_deploy_env):
    env, state_dir = fake_deploy_env

    result = _run(env, app="some-other-app")

    assert result.returncode == 64
    assert "must exactly match fly.toml app" in result.stderr
    assert not (state_dir / "calls.jsonl").exists()


@pytest.mark.unit
def test_unmerged_commit_requires_explicit_reviewed_override(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_REMOTE_REVISION"] = "b" * 40

    rejected = _run(env)
    assert rejected.returncode == 65
    assert "requires HEAD to exactly match the configured remote branch" in rejected.stderr
    assert not (state_dir / "calls.jsonl").exists()

    env["COLLECTOR_DEPLOY_ALLOW_UNMERGED"] = "true"
    accepted = _run(env)
    assert accepted.returncode == 0, accepted.stderr
    remote_reads = [call for call in _git_calls(state_dir) if call[:1] == ["ls-remote"]]
    assert len(remote_reads) == 1


@pytest.mark.unit
def test_remote_branch_is_authoritative_over_stale_local_tracking_ref(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_LOCAL_TARGET_REVISION"] = "b" * 40
    env["FAKE_REMOTE_REVISION"] = REVISION

    result = _run(env)

    assert result.returncode == 0, result.stderr
    rev_parses = [call for call in _git_calls(state_dir) if call[:1] == ["rev-parse"]]
    assert rev_parses == [["rev-parse", "--verify", "HEAD"]]


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["unavailable", "malformed"])
def test_unavailable_or_malformed_remote_fails_closed_without_leaking_output(
    mode, fake_deploy_env
):
    env, state_dir = fake_deploy_env
    env["FAKE_REMOTE_MODE"] = mode

    result = _run(env)

    assert result.returncode == 65
    assert "cannot authenticate and resolve" in result.stderr
    assert "remote-secret" not in result.stdout + result.stderr
    assert _deploy_calls(state_dir) == []


@pytest.mark.unit
def test_remote_change_after_snapshot_aborts_before_fly_deploy(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_REMOTE_REVISION_AFTER"] = "b" * 40

    result = _run(env)

    assert result.returncode == 75
    assert "changed or became unverifiable before deployment" in result.stderr
    assert _deploy_calls(state_dir) == []
    remote_reads = [call for call in _git_calls(state_dir) if call[:1] == ["ls-remote"]]
    assert len(remote_reads) == 2
