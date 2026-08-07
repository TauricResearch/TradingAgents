"""Behavioral tests for the collector's transactional Fly deploy wrapper."""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import subprocess
import sys
import textwrap
import threading
import time
from contextlib import suppress
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "scripts" / "deploy_collector.sh"
UNLOCK = ROOT / "scripts" / "unlock_collector_deploy.sh"
REVISION = "a" * 40


FAKE_GIT = r"""#!/usr/bin/env python3
import json
import os
import pathlib
import sys

state_dir = pathlib.Path(os.environ["FAKE_STATE_DIR"])
args = sys.argv[1:]
with (state_dir / "git-calls.jsonl").open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\n")

if (
    args
    and args[0] in {"remote", "ls-remote", "push"}
    and os.environ.get("FAKE_REQUIRE_GIT_TRACE_DISABLED") == "true"
):
    disabled = (
        "GIT_TRACE", "GIT_TRACE_PACK_ACCESS", "GIT_TRACE_PACKET",
        "GIT_TRACE_PERFORMANCE", "GIT_TRACE_SETUP", "GIT_TRACE_SHALLOW",
        "GIT_TRACE_CURL", "GIT_TRACE2", "GIT_TRACE2_EVENT", "GIT_TRACE2_PERF",
    )
    if any(os.environ.get(name) != "0" for name in disabled):
        print("git trace was not disabled", file=sys.stderr)
        raise SystemExit(2)

if args == ["status", "--porcelain"]:
    raise SystemExit(0)
if args == ["rev-parse", "--verify", "HEAD"]:
    print(os.environ["FAKE_REVISION"])
    raise SystemExit(0)
if args[:2] == ["rev-parse", "--verify"]:
    print(os.environ.get("FAKE_LOCAL_TARGET_REVISION", os.environ["FAKE_REVISION"]))
    raise SystemExit(0)
if args and args[0] == "check-ref-format":
    invalid_target = (
        os.environ.get("FAKE_INVALID_TARGET") == "true"
        and args[-1] == "refs/heads/main"
    )
    raise SystemExit(1 if invalid_target else 0)
if args[:3] == ["remote", "get-url", "--push"]:
    if os.environ.get("FAKE_LOCK_REMOTE_UNAVAILABLE") == "true":
        print(
            "fatal: https://user:remote-secret@example.invalid/repo.git",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if os.environ.get("FAKE_LOCK_MULTIPLE_PUSHURLS") == "true":
        print("https://github.com/clarkipeng/TradingAgents.git")
        print("https://github.com/attacker/TradingAgents.git")
    else:
        print(os.environ.get(
            "FAKE_LOCK_REMOTE_URL",
            "https://github.com/clarkipeng/TradingAgents.git",
        ))
    raise SystemExit(0)
if args == ["mktree"]:
    sys.stdin.read()
    print("e" * 40)
    raise SystemExit(0)
if args and args[0] == "commit-tree":
    sys.stdin.read()
    print(os.environ.get("FAKE_LOCK_COMMIT", "c" * 40))
    raise SystemExit(0)
if args and args[0] == "push":
    lock_path = state_dir / "remote-lock"
    ref = "refs/heads/tradingagents-deploy-lock/tradagent"
    if args[-1] == f":{ref}":
        if os.environ.get("FAKE_LOCK_CLEANUP_RACE") == "true":
            lock_path.write_text("d" * 40)
        lease = next(
            (item for item in args if item.startswith("--force-with-lease=")),
            "",
        )
        expected = lease.rpartition(":")[2]
        current = lock_path.read_text() if lock_path.exists() else ""
        if (
            current != expected
            or os.environ.get("FAKE_LOCK_CLEANUP_FAILURE") == "true"
        ):
            print(
                "rejected https://user:remote-secret@example.invalid/repo.git",
                file=sys.stderr,
            )
            raise SystemExit(1)
        lock_path.unlink()
        (state_dir / "delete-accepted").write_text("true")
        if os.environ.get("FAKE_LOCK_DELETE_LOST_ACK") == "true":
            print(
                "lost response https://user:remote-secret@example.invalid/repo.git",
                file=sys.stderr,
            )
            raise SystemExit(1)
        raise SystemExit(0)
    proposed, separator, proposed_ref = args[-1].partition(":")
    if os.environ.get("FAKE_LOCK_RACE_ON_PUSH") == "true":
        lock_path.write_text("d" * 40)
        print(
            "rejected https://user:remote-secret@example.invalid/repo.git",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if (
        not separator
        or proposed_ref != ref
        or os.environ.get("FAKE_LOCK_PUSH_REJECTED") == "true"
        or lock_path.exists()
    ):
        print(
            "rejected https://user:remote-secret@example.invalid/repo.git",
            file=sys.stderr,
        )
        raise SystemExit(1)
    lock_path.write_text(proposed)
    if os.environ.get("FAKE_LOCK_LOST_CREATE_ACK") == "true":
        print(
            "lost response https://user:remote-secret@example.invalid/repo.git",
            file=sys.stderr,
        )
        raise SystemExit(1)
    raise SystemExit(0)
if args and args[0] == "ls-remote" and "--refs" in args:
    requested_ref = args[-1]
    if requested_ref.startswith("refs/heads/tradingagents-deploy-lock/"):
        lock_path = state_dir / "remote-lock"
        count_path = state_dir / "lock-read-count"
        count = int(count_path.read_text()) if count_path.exists() else 0
        count_path.write_text(str(count + 1))
        if os.environ.get("FAKE_LOCK_CONTENDED") == "true" and not lock_path.exists():
            lock_path.write_text("d" * 40)
        if (
            not lock_path.exists()
            and os.environ.get("FAKE_LOCK_POST_DELETE_UNAVAILABLE_ONCE") == "true"
            and (state_dir / "delete-accepted").exists()
            and not (state_dir / "post-delete-unavailable-used").exists()
        ):
            (state_dir / "post-delete-unavailable-used").write_text("true")
            print(
                "transport https://user:remote-secret@example.invalid/repo.git",
                file=sys.stderr,
            )
            raise SystemExit(2)
        lost_after = int(os.environ.get("FAKE_LOCK_LOST_AFTER", "-1"))
        if lost_after >= 0 and count >= lost_after and lock_path.exists():
            lock_path.write_text("d" * 40)
        if not lock_path.exists():
            raise SystemExit(2 if "--exit-code" in args else 0)
        print(f"{lock_path.read_text()}\t{requested_ref}")
        raise SystemExit(0)
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
    print(f"{revision}\t{requested_ref}")
    raise SystemExit(0)

print("unexpected fake git invocation", args, file=sys.stderr)
raise SystemExit(2)
"""


FAKE_FLY = r'''#!/usr/bin/env python3
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

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
    if kind in {"previous", "previous-mutated-config"}:
        machine_id = "machine-old"
        instance_id = "instance-old-000"
        image = "registry.fly.io/tradagent:deployment-previous"
        digest = "sha256:" + "1" * 64
        release = "release-old"
        release_version = "33"
        env = {
            "FLY_PROCESS_GROUP": "app",
            "MEDIA_AUTO_MIGRATE": "false",
            "MEDIA_COLLECTION_ENABLED": "true",
        }
        if kind == "previous-mutated-config":
            env["CONCURRENT_CONFIG"] = "true"
        restart = {"policy": "on-failure", "max_retries": 10}
    elif kind in {"target", "target-new-release", "target-mutated-config"}:
        machine_id = "machine-old"
        instance_id = (
            "instance-concurrent-000"
            if kind in {"target-new-release", "target-mutated-config"}
            else "instance-new-000"
        )
        target_image_path = state_dir / "target-image"
        if not target_image_path.exists():
            raise SystemExit("target image was not recorded")
        image = target_image_path.read_text()
        digest = "sha256:" + "2" * 64
        release = "release-new"
        release_version = (
            "37"
            if scenario in {"interposed_predecessor", "baseline_after_fenced_rollback"}
            else "36"
        )
        env = {
            "FLY_PROCESS_GROUP": "app",
            "MEDIA_AUTO_MIGRATE": "false",
            "MEDIA_COLLECTION_ENABLED": "true",
            "MEDIA_HEALTH_PORT": "5500",
        }
        if kind == "target-new-release":
            release = "release-concurrent"
            release_version = "37"
            env["CONCURRENT_RELEASE"] = "true"
        elif kind == "target-mutated-config":
            env["CONCURRENT_CONFIG"] = "true"
        restart = {"policy": "always"}
    else:
        machine_id = "machine-foreign"
        instance_id = "instance-foreign-000"
        image = (
            f"registry.fly.io/tradagent:git-{revision}-" + "f" * 32
            if kind == "foreign-same-commit"
            else "registry.fly.io/tradagent:git-" + "b" * 40
        )
        digest = "sha256:" + "3" * 64
        release = "release-foreign"
        release_version = "37"
        env = {"FLY_PROCESS_GROUP": "app", "MEDIA_HEALTH_PORT": "5500"}
        restart = {"policy": "always"}
    metadata = {
        "fly_process_group": "app",
        "fly_release_id": release,
        "fly_release_version": release_version,
    }
    if scenario == "baseline_after_fenced_rollback" and kind in {
        "previous", "target",
    }:
        metadata.update({
            "tradingagents_fenced_rollback_from_release_version": "36",
            "tradingagents_fenced_rollback_to_release_version": "33",
        })
    return {
        "id": machine_id,
        "instance_id": instance_id,
        "state": "started",
        "image_ref": {"digest": digest},
        "config": {
            "image": image,
            "metadata": metadata,
            "env": env,
            "init": {"cmd": ["--global-only"]},
            "guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 256},
            "restart": restart,
        },
    }

if args[:2] == ["config", "validate"]:
    if scenario == "hang_after_lock":
        (state_dir / "hang-after-lock").write_text(str(os.getpid()))
        while os.getppid() != 1:
            time.sleep(0.05)
    raise SystemExit(0)
if args[:2] == ["config", "save"]:
    pathlib.Path(value("-c")).write_text(
        "app = 'tradagent'\n[processes]\n  app = '--global-only'\n",
        encoding="utf-8",
    )
    raise SystemExit(0)
if args[:2] == ["auth", "token"]:
    print("test-fly-token-never-render")
    raise SystemExit(0)
if args and args[0] == "status":
    superseding_kind = {
        "superseded": "foreign",
        "superseded_same_commit": "foreign-same-commit",
        "superseded_same_image": "target-new-release",
        "superseded_config_only": "target-mutated-config",
    }.get(scenario)
    if scenario == "baseline_superseded_before_deploy" and phase == "previous":
        counter_path = state_dir / "baseline-status-count"
        count = int(counter_path.read_text()) if counter_path.exists() else 0
        counter_path.write_text(str(count + 1))
        # Snapshot capture is stable, then a config-only release wins while the
        # wrapper performs its baseline health and remote-ref checks.
        kind = "previous" if count < 2 else "previous-mutated-config"
    elif superseding_kind is not None and phase == "target":
        counter_path = state_dir / "target-status-count"
        count = int(counter_path.read_text()) if counter_path.exists() else 0
        counter_path.write_text(str(count + 1))
        # The first status identifies our target; the next proves a newer release.
        kind = "target" if count == 0 else superseding_kind
    else:
        kind = phase
    machines = [] if phase == "empty" else [machine(kind)]
    print(json.dumps({"Machines": machines}))
    raise SystemExit(0)
if args and args[0] == "releases":
    if scenario == "release_history_unavailable":
        raise SystemExit(1)
    if scenario == "release_history_malformed":
        print(json.dumps({"releases": "not-an-authenticated-list"}))
        raise SystemExit(0)
    rows = [
        {"Version": 35, "Status": "failed"},
        {"Version": 34, "Status": "failed"},
        {"Version": 33, "Status": "complete"},
    ]
    if phase == "target":
        if scenario in {"interposed_predecessor", "baseline_after_fenced_rollback"}:
            rows = [
                {"Version": 37, "Status": "complete"},
                {"Version": 36, "Status": "complete"},
                *rows,
            ]
        else:
            rows = [{"Version": 36, "Status": "complete"}, *rows]
    print(json.dumps(rows))
    raise SystemExit(0)
if args and args[0] == "deploy":
    image_label = value("--image-label")
    (state_dir / "target-image").write_text(
        f"registry.fly.io/tradagent:{image_label}", encoding="utf-8"
    )
    if scenario == "deploy_failure_unchanged":
        raise SystemExit(1)
    if scenario == "deploy_failure_delayed_candidate":
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import pathlib,sys,time; time.sleep(0.25); "
                    "pathlib.Path(sys.argv[1]).write_text('target')"
                ),
                str(phase_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        raise SystemExit(1)
    if scenario == "deploy_failure_no_machine":
        phase_path.write_text("empty")
        raise SystemExit(1)
    phase_path.write_text("target")
    if scenario == "signal_during_deploy":
        os.kill(os.getppid(), signal.SIGTERM)
        time.sleep(30)
        raise SystemExit(143)
    if scenario == "deploy_failure_changed":
        raise SystemExit(1)
    raise SystemExit(0)
if args[:2] == ["checks", "list"]:
    baseline_status = (
        "critical"
        if scenario in {"baseline_unhealthy", "legacy_baseline_health_timeout"}
        else "passing"
    )
    checks = {
        "machine-old": [{"name": "collector_health", "status": baseline_status}]
    }
    if phase == "target":
        if scenario == "wrong_machine_check":
            checks = {
                "not-the-target": [
                    {"name": "collector_health", "status": "passing"}
                ]
            }
        else:
            target_status = (
                "critical"
                if scenario in {
                    "health_timeout", "interposed_predecessor",
                    "rollback_fenced_race", "fenced_rollback_failure",
                    "legacy_baseline_health_timeout",
                }
                else "passing"
            )
            checks["machine-old"] = [
                {"name": "collector_health", "status": target_status}
            ]
    print(json.dumps(checks))
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
    fake_python = bin_dir / "python3"
    fake_python.write_text(textwrap.dedent(f"""\
        #!{sys.executable}
        import json
        import os
        import pathlib
        import sys

        args = sys.argv[1:]
        state_dir = pathlib.Path(os.environ["FAKE_STATE_DIR"])
        if args and pathlib.Path(args[0]).name == "fenced_machine_rollback.py":
            with (state_dir / "rollback-helper-calls.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write(json.dumps(args[1:]) + "\\n")
            scenario = os.environ.get("FAKE_SCENARIO")
            if scenario == "rollback_fenced_race":
                (state_dir / "phase").write_text("foreign")
            if scenario in {{"fenced_rollback_failure", "rollback_fenced_race"}}:
                print("fenced Fly rollback failed (OwnershipChanged)", file=sys.stderr)
                raise SystemExit(1)
            (state_dir / "phase").write_text("previous")
            print("fenced Fly rollback verified")
            raise SystemExit(0)
        real_python = os.environ["REAL_PYTHON"]
        os.execv(real_python, [real_python, *args])
    """), encoding="utf-8")
    fake_python.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "TMPDIR": str(tmp_path),
        "FAKE_STATE_DIR": str(state_dir),
        "FAKE_REVISION": REVISION,
        "REAL_PYTHON": sys.executable,
        "COLLECTOR_HEALTH_TIMEOUT_SECONDS": "1",
        "COLLECTOR_HEALTH_POLL_SECONDS": "1",
        "COLLECTOR_ROLLBACK_TIMEOUT_SECONDS": "1",
        "COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE": "false",
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


def _run_with_xtrace(env):
    return subprocess.run(
        ["bash", "-x", str(DEPLOY), "tradagent"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _run_unlock(env, mode, owner=None, *, xtrace=False):
    command = [str(UNLOCK), mode, "tradagent"]
    if owner is not None:
        command.append(owner)
    if xtrace:
        command = ["bash", "-x", *command]
    return subprocess.run(
        command,
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


def _target_remote_reads(state_dir):
    return [
        call
        for call in _git_calls(state_dir)
        if call[:1] == ["ls-remote"] and call[-1] == "refs/heads/main"
    ]


def _lock_remote_reads(state_dir):
    return [
        call
        for call in _git_calls(state_dir)
        if call[:1] == ["ls-remote"]
        and call[-1] == "refs/heads/tradingagents-deploy-lock/tradagent"
    ]


def _lock_pushes(state_dir):
    return [call for call in _git_calls(state_dir) if call[:1] == ["push"]]


def _deploy_calls(state_dir):
    return [call for call in _calls(state_dir) if call and call[0] == "deploy"]


def _rollback_helper_calls(state_dir):
    path = state_dir / "rollback-helper-calls.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.unit
def test_success_is_bound_to_target_machine_check_and_exact_revision(fake_deploy_env):
    env, state_dir = fake_deploy_env

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert f"healthy at {REVISION} on Machine machine-old" in result.stdout
    deploys = _deploy_calls(state_dir)
    assert len(deploys) == 1
    assert ["--build-arg", f"GIT_REVISION={REVISION}"] == deploys[0][
        deploys[0].index("--build-arg"):deploys[0].index("--build-arg") + 2
    ]
    image_label = deploys[0][deploys[0].index("--image-label") + 1]
    assert re.fullmatch(rf"git-{REVISION}-[0-9a-f]{{32}}", image_label)
    ssh_call = next(call for call in _calls(state_dir) if call[:2] == ["ssh", "console"])
    assert ssh_call[ssh_call.index("--machine") + 1] == "machine-old"
    assert REVISION in ssh_call[ssh_call.index("-C") + 1]
    assert _target_remote_reads(state_dir) == [
        ["ls-remote", "--exit-code", "--refs", "origin", "refs/heads/main"],
        ["ls-remote", "--exit-code", "--refs", "origin", "refs/heads/main"],
    ]
    lock_ref = "refs/heads/tradingagents-deploy-lock/tradagent"
    lock_commit = "c" * 40
    lock_url = "https://github.com/clarkipeng/TradingAgents.git"
    pushes = _lock_pushes(state_dir)
    assert pushes == [
        ["push", "--no-verify", lock_url, f"{lock_commit}:{lock_ref}"],
        [
            "push",
            "--no-verify",
            f"--force-with-lease={lock_ref}:{lock_commit}",
            lock_url,
            f":{lock_ref}",
        ],
    ]
    assert _lock_remote_reads(state_dir)


@pytest.mark.unit
def test_fenced_rollback_lineage_allows_the_next_serial_deploy(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "baseline_after_fenced_rollback"

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert len(_deploy_calls(state_dir)) == 1
    assert _rollback_helper_calls(state_dir) == []


@pytest.mark.unit
def test_primary_deploy_failure_uses_one_fenced_machine_rollback(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "deploy_failure_changed"

    result = _run(env)

    assert result.returncode == 1
    assert "deployment command failed" in result.stderr
    assert "previous collector image and configuration restored" in result.stdout
    deploys = _deploy_calls(state_dir)
    assert len(deploys) == 1
    helper_calls = _rollback_helper_calls(state_dir)
    assert len(helper_calls) == 1
    helper = helper_calls[0]
    assert helper[helper.index("--expected-instance") + 1] == "instance-new-000"
    assert helper[helper.index("--expected-image") + 1].startswith(
        f"registry.fly.io/tradagent:git-{REVISION}-"
    )
    assert helper[helper.index("--baseline-release-version") + 1] == "33"
    assert helper[helper.index("--baseline-machine-id") + 1] == "machine-old"
    assert helper[helper.index("--baseline-instance") + 1] == "instance-old-000"
    assert helper[helper.index("--baseline-image") + 1].endswith(
        ":deployment-previous"
    )
    assert helper[helper.index("--baseline-digest") + 1] == "sha256:" + "1" * 64
    assert helper[helper.index("--baseline-release") + 1] == "release-old"
    assert re.fullmatch(
        r"[0-9a-f]{64}",
        helper[helper.index("--baseline-config-fingerprint") + 1],
    )
    assert "--allow-legacy-baseline-on-failure" not in helper
    assert helper[helper.index("--previous-status") + 1].endswith(
        "status.previous.json"
    )
    assert "test-fly-token-never-render" not in json.dumps(helper_calls)


@pytest.mark.unit
def test_inherited_shell_xtrace_never_renders_fly_token(fake_deploy_env):
    env, _state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "deploy_failure_changed"
    canary = "fly-secret-xtrace-canary-never-render"
    env["FLY_API_TOKEN"] = canary

    result = _run_with_xtrace(env)

    assert result.returncode == 1
    assert canary not in result.stdout + result.stderr
    assert "fly-secret" not in result.stdout + result.stderr


@pytest.mark.unit
def test_pre_mutation_deploy_failure_leaves_known_good_release_alone(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "deploy_failure_unchanged"

    result = _run(env)

    assert result.returncode == 1
    assert len(_deploy_calls(state_dir)) == 1
    assert "failed mutation may still complete" in result.stderr
    assert (state_dir / "remote-lock").read_text() == "c" * 40


@pytest.mark.unit
def test_delayed_candidate_after_failed_deploy_ack_keeps_remote_lock(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "deploy_failure_delayed_candidate"

    result = _run(env)

    assert result.returncode == 1
    assert "failed mutation may still complete" in result.stderr
    deadline = time.monotonic() + 2
    phase_path = state_dir / "phase"
    while (
        time.monotonic() < deadline
        and (not phase_path.exists() or phase_path.read_text() != "target")
    ):
        time.sleep(0.02)
    assert phase_path.read_text() == "target"
    assert (state_dir / "remote-lock").read_text() == "c" * 40
    cleanup_pushes = [
        call
        for call in _lock_pushes(state_dir)
        if any(item.startswith("--force-with-lease=") for item in call)
    ]
    assert cleanup_pushes == []


@pytest.mark.unit
def test_unbound_empty_state_after_deploy_failure_refuses_rollback(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "deploy_failure_no_machine"

    result = _run(env)

    assert result.returncode == 1
    assert len(_deploy_calls(state_dir)) == 1
    assert "deployment command failed" in result.stderr
    assert "refusing to roll back a newer release" in result.stderr


@pytest.mark.unit
@pytest.mark.parametrize("scenario", ["health_timeout", "wrong_machine_check", "revision_mismatch"])
def test_unverified_target_rolls_back(scenario, fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario

    result = _run(env)

    assert result.returncode == 1
    assert len(_deploy_calls(state_dir)) == 1
    assert len(_rollback_helper_calls(state_dir)) == 1
    assert "previous collector image and configuration restored" in result.stdout


@pytest.mark.unit
@pytest.mark.parametrize(
    "scenario",
    [
        "superseded",
        "superseded_same_commit",
        "superseded_same_image",
        "superseded_config_only",
    ],
)
def test_superseding_release_is_never_rolled_back(scenario, fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario

    result = _run(env)

    assert result.returncode == 75
    assert len(_deploy_calls(state_dir)) == 1
    assert "superseded" in result.stderr
    assert "refusing to roll back a newer release" in result.stderr


@pytest.mark.unit
def test_unhealthy_baseline_fails_before_deploy_without_break_glass(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "baseline_unhealthy"

    result = _run(env)

    assert result.returncode == 69
    assert _deploy_calls(state_dir) == []
    assert "requires a passing baseline collector_health check" in result.stderr
    assert "COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE=true" in result.stderr


@pytest.mark.unit
def test_unhealthy_baseline_requires_loud_one_run_break_glass(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "baseline_unhealthy"
    env["COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE"] = "true"

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert len(_deploy_calls(state_dir)) == 1
    assert "WARNING: break-glass deployment" in result.stderr
    assert "cannot certify it healthy" in result.stderr


@pytest.mark.unit
def test_legacy_break_glass_is_forwarded_only_to_fenced_baseline_restore(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "legacy_baseline_health_timeout"
    env["COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE"] = "true"

    result = _run(env)

    assert result.returncode == 1
    helper = _rollback_helper_calls(state_dir)[0]
    assert helper.count("--allow-legacy-baseline-on-failure") == 1


@pytest.mark.unit
def test_unhealthy_baseline_override_requires_explicit_boolean(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE"] = "sometimes"

    result = _run(env)

    assert result.returncode == 64
    assert _deploy_calls(state_dir) == []
    assert "must be an explicit boolean" in result.stderr


@pytest.mark.unit
def test_baseline_config_race_aborts_before_deploy(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "baseline_superseded_before_deploy"

    result = _run(env)

    assert result.returncode == 75
    assert _deploy_calls(state_dir) == []
    assert "changed after baseline verification" in result.stderr


@pytest.mark.unit
def test_interposed_complete_release_prevents_stale_baseline_rollback(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "interposed_predecessor"

    result = _run(env)

    assert result.returncode == 1
    assert len(_deploy_calls(state_dir)) == 1
    assert "candidate predecessor is not the saved baseline" in result.stderr
    assert "restoring the previous collector" not in result.stderr


@pytest.mark.unit
@pytest.mark.parametrize(
    "scenario", ["release_history_unavailable", "release_history_malformed"],
)
def test_unverifiable_release_history_fails_closed_without_rollback(
    scenario, fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario

    result = _run(env)

    assert result.returncode == 75
    assert len(_deploy_calls(state_dir)) == 1
    assert "candidate predecessor is not the saved baseline" in result.stderr
    assert "restoring the previous collector" not in result.stderr


@pytest.mark.unit
@pytest.mark.parametrize(
    "scenario", ["rollback_fenced_race", "fenced_rollback_failure"],
)
def test_fenced_rollback_failure_has_no_unconditional_fallback(
    scenario, fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario

    result = _run(env)

    assert result.returncode == 1
    assert len(_deploy_calls(state_dir)) == 1
    assert len(_rollback_helper_calls(state_dir)) == 1
    assert "automatic fenced rollback failed" in result.stderr
    if scenario == "rollback_fenced_race":
        assert (state_dir / "phase").read_text() == "foreign"
    assert "test-fly-token-never-render" not in result.stdout + result.stderr


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
    assert len(_deploy_calls(state_dir)) == 1
    assert len(_rollback_helper_calls(state_dir)) == 1
    assert "interrupted by TERM" in result.stderr
    assert "previous collector image and configuration restored" in result.stdout


@pytest.mark.unit
def test_signal_during_mutator_preserves_remote_lock_and_never_rolls_back(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "signal_during_deploy"

    result = _run(env)

    assert result.returncode == 143
    assert len(_deploy_calls(state_dir)) == 1
    assert _rollback_helper_calls(state_dir) == []
    assert "mutation was interrupted" in result.stderr
    assert "lock is preserved" in result.stderr
    assert (state_dir / "remote-lock").read_text() == "c" * 40
    cleanup_pushes = [
        call
        for call in _lock_pushes(state_dir)
        if any(item.startswith("--force-with-lease=") for item in call)
    ]
    assert cleanup_pushes == []


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
    assert len(_target_remote_reads(state_dir)) == 1


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
    assert len(_target_remote_reads(state_dir)) == 2


@pytest.mark.unit
def test_remote_deploy_lock_contention_aborts_before_fly_without_leaks(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_ALLOW_UNMERGED"] = "true"
    env["FAKE_LOCK_CONTENDED"] = "true"

    result = _run(env)

    assert result.returncode == 73
    assert "another host owns" in result.stderr
    assert "remote-secret" not in result.stdout + result.stderr
    assert not (state_dir / "calls.jsonl").exists()
    assert _lock_pushes(state_dir) == []


@pytest.mark.unit
def test_simultaneous_remote_lock_race_has_one_atomic_loser(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_ALLOW_UNMERGED"] = "true"
    env["FAKE_LOCK_RACE_ON_PUSH"] = "true"

    result = _run(env)

    assert result.returncode == 73
    assert "another host owns" in result.stderr
    assert _deploy_calls(state_dir) == []
    assert (state_dir / "remote-lock").read_text() == "d" * 40
    assert "remote-secret" not in result.stdout + result.stderr


@pytest.mark.unit
def test_rejected_lock_create_with_absent_ref_fails_ambiguous(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_ALLOW_UNMERGED"] = "true"
    env["FAKE_LOCK_PUSH_REJECTED"] = "true"

    result = _run(env)

    assert result.returncode == 75
    assert "was not acquired" in result.stderr
    assert _deploy_calls(state_dir) == []
    assert "remote-secret" not in result.stdout + result.stderr


@pytest.mark.unit
def test_remote_deploy_lock_cleanup_is_exact_and_fails_loudly_on_race(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_LOCK_CLEANUP_RACE"] = "true"

    result = _run(env)

    assert result.returncode == 0
    assert "healthy at" in result.stdout
    assert "remote-secret" not in result.stdout + result.stderr
    assert (state_dir / "remote-lock").read_text() == "d" * 40


@pytest.mark.unit
def test_unreleased_owned_remote_lock_turns_success_into_failure(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_LOCK_CLEANUP_FAILURE"] = "true"

    result = _run(env)

    assert result.returncode == 74
    assert "healthy at" in result.stdout
    assert "remote deploy lock was not released" in result.stderr
    assert (state_dir / "remote-lock").read_text() == "c" * 40
    assert "remote-secret" not in result.stdout + result.stderr


@pytest.mark.unit
def test_lost_remote_lock_never_rolls_back_or_deletes_new_owner(fake_deploy_env):
    env, state_dir = fake_deploy_env
    # Pre-read is 0, acquire reconciliation is 1, the pre-mutation check is 2,
    # and the first post-deploy verification sees the new owner at read 3.
    env["FAKE_LOCK_LOST_AFTER"] = "3"

    result = _run(env)

    assert result.returncode == 75
    assert "lock ownership was lost during verification" in result.stderr
    assert _rollback_helper_calls(state_dir) == []
    assert (state_dir / "phase").read_text() == "target"
    assert (state_dir / "remote-lock").read_text() == "d" * 40
    assert "remote-secret" not in result.stdout + result.stderr


@pytest.mark.unit
def test_lock_remote_must_be_explicitly_valid_and_writable(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_ALLOW_UNMERGED"] = "true"
    env["COLLECTOR_DEPLOY_LOCK_REMOTE"] = "invalid/remote"

    result = _run(env)

    assert result.returncode == 64
    assert "shared writable deployment remote" in result.stderr
    assert not (state_dir / "calls.jsonl").exists()


@pytest.mark.unit
def test_lost_lock_create_ack_is_reconciled_without_retry_or_secret_leak(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_LOCK_LOST_CREATE_ACK"] = "true"

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert "reconciled an acknowledged remote lock" in result.stderr
    acquire_pushes = [
        call
        for call in _lock_pushes(state_dir)
        if not any(item.startswith("--force-with-lease=") for item in call)
    ]
    assert len(acquire_pushes) == 1
    assert "remote-secret" not in result.stdout + result.stderr


@pytest.mark.unit
def test_inherited_git_trace2_targets_are_disabled_for_transport(fake_deploy_env):
    env, state_dir = fake_deploy_env
    trace_target = state_dir / "credential-bearing-trace.json"
    env.update({
        "FAKE_REQUIRE_GIT_TRACE_DISABLED": "true",
        "GIT_TRACE": str(trace_target),
        "GIT_TRACE2": str(trace_target),
        "GIT_TRACE2_EVENT": str(trace_target),
        "GIT_TRACE2_PERF": str(trace_target),
    })

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert not trace_target.exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    "remote_url",
    [
        "https://token@github.com/clarkipeng/TradingAgents.git",
        "https://github.com/another/TradingAgents.git",
        "https://github.com/clarkipeng/TradingAgents.git?token=private",
    ],
)
def test_lock_remote_rejects_credentials_or_wrong_canonical_repo(
    remote_url, fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_ALLOW_UNMERGED"] = "true"
    env["FAKE_LOCK_REMOTE_URL"] = remote_url

    result = _run(env)

    assert result.returncode == 64
    assert _deploy_calls(state_dir) == []
    assert remote_url not in result.stdout + result.stderr
    assert "token" not in result.stdout + result.stderr


@pytest.mark.unit
def test_multiple_lock_push_urls_fail_before_fly(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_ALLOW_UNMERGED"] = "true"
    env["FAKE_LOCK_MULTIPLE_PUSHURLS"] = "true"

    result = _run(env)

    assert result.returncode == 64
    assert _deploy_calls(state_dir) == []


@pytest.mark.unit
def test_real_git_remote_lock_has_one_winner_and_exact_cleanup(tmp_path):
    bare = tmp_path / "shared.git"
    subprocess.run(
        ["git", "init", "--bare", str(bare)],
        check=True,
        capture_output=True,
        text=True,
    )
    owners = []
    identity = {
        **os.environ,
        "GIT_AUTHOR_NAME": "TradingAgents",
        "GIT_AUTHOR_EMAIL": "deploy-lock@localhost",
        "GIT_COMMITTER_NAME": "TradingAgents",
        "GIT_COMMITTER_EMAIL": "deploy-lock@localhost",
    }
    for ordinal in range(2):
        repo = tmp_path / f"owner-{ordinal}"
        subprocess.run(
            ["git", "init", str(repo)],
            check=True,
            capture_output=True,
            text=True,
        )
        tree = subprocess.run(
            ["git", "mktree"],
            cwd=repo,
            input="",
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        owner = subprocess.run(
            ["git", "commit-tree", tree],
            cwd=repo,
            env=identity,
            input=f"schema=v1 nonce={ordinal}\n",
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        owners.append((repo, owner))

    lock_ref = "refs/heads/tradingagents-deploy-lock/tradagent"
    barrier = threading.Barrier(2)

    def acquire(candidate):
        repo, owner = candidate
        barrier.wait()
        result = subprocess.run(
            ["git", "push", "--no-verify", str(bare), f"{owner}:{lock_ref}"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode, repo, owner

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(acquire, owners))
    winner = next(result for result in results if result[0] == 0)
    loser = next(result for result in results if result[0] != 0)
    assert sorted(result[0] == 0 for result in results) == [False, True]
    for repo, _owner in owners:
        assert subprocess.run(
            ["git", "for-each-ref", "--format=%(refname)"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout == ""

    winner_repo, winner_oid = winner[1:]
    subprocess.run(
        [
            "git",
            "push",
            "--no-verify",
            f"--force-with-lease={lock_ref}:{winner_oid}",
            str(bare),
            f":{lock_ref}",
        ],
        cwd=winner_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    loser_repo, loser_oid = loser[1:]
    subprocess.run(
        ["git", "push", "--no-verify", str(bare), f"{loser_oid}:{lock_ref}"],
        cwd=loser_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    stale_cleanup = subprocess.run(
        [
            "git",
            "push",
            "--no-verify",
            f"--force-with-lease={lock_ref}:{winner_oid}",
            str(bare),
            f":{lock_ref}",
        ],
        cwd=winner_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert stale_cleanup.returncode != 0
    observed = subprocess.run(
        ["git", "ls-remote", "--refs", str(bare), lock_ref],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert observed == f"{loser_oid}\t{lock_ref}\n"


@pytest.mark.unit
def test_sigkill_leaves_stale_remote_lock_that_blocks_next_host(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_ALLOW_UNMERGED"] = "true"
    env["FAKE_SCENARIO"] = "hang_after_lock"
    process = subprocess.Popen(
        [str(DEPLOY), "tradagent"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not (state_dir / "hang-after-lock").exists():
        time.sleep(0.02)
    assert (state_dir / "hang-after-lock").exists()
    process.kill()
    process.wait(timeout=5)
    child_pid = int((state_dir / "hang-after-lock").read_text())
    with suppress(ProcessLookupError):
        os.kill(child_pid, 9)
    process.communicate(timeout=5)
    assert process.returncode < 0
    assert (state_dir / "remote-lock").read_text() == "c" * 40

    # A different host has no local lock directory but shares the remote ref.
    local_lock = Path(env["TMPDIR"]) / "tradingagents-tradagent.deploy.lock"
    if local_lock.exists():
        for child in local_lock.iterdir():
            child.unlink()
        local_lock.rmdir()
    env["FAKE_SCENARIO"] = "success"
    retried = _run(env)
    assert retried.returncode == 73
    assert "another host owns" in retried.stderr
    assert _deploy_calls(state_dir) == []


@pytest.mark.unit
def test_safe_unlock_inspects_and_exactly_releases_remote_owner(fake_deploy_env):
    env, state_dir = fake_deploy_env
    owner = "c" * 40
    (state_dir / "remote-lock").write_text(owner)

    inspected = _run_unlock(env, "inspect")
    released = _run_unlock(env, "release", owner)

    assert inspected.returncode == 0
    assert owner in inspected.stdout
    assert released.returncode == 0, released.stderr
    assert "stale deploy lock released" in released.stdout
    assert not (state_dir / "remote-lock").exists()
    cleanup = _lock_pushes(state_dir)[0]
    lock_ref = "refs/heads/tradingagents-deploy-lock/tradagent"
    assert f"--force-with-lease={lock_ref}:{owner}" in cleanup
    assert "--no-verify" in cleanup


@pytest.mark.unit
def test_safe_unlock_removes_only_verified_dead_local_owner(fake_deploy_env):
    env, state_dir = fake_deploy_env
    owner = "c" * 40
    (state_dir / "remote-lock").write_text(owner)
    local_lock = Path(env["TMPDIR"]) / "tradingagents-tradagent.deploy.lock"
    local_lock.mkdir()
    (local_lock / "owner").write_text(f"pid=99999999 revision={REVISION}\n")

    result = _run_unlock(env, "release", owner)

    assert result.returncode == 0, result.stderr
    assert not local_lock.exists()


@pytest.mark.unit
def test_safe_unlock_reconciles_lost_delete_ack_in_same_run(fake_deploy_env):
    env, state_dir = fake_deploy_env
    owner = "c" * 40
    (state_dir / "remote-lock").write_text(owner)
    local_lock = Path(env["TMPDIR"]) / "tradingagents-tradagent.deploy.lock"
    local_lock.mkdir()
    (local_lock / "owner").write_text(f"pid=99999999 revision={REVISION}\n")
    env["FAKE_LOCK_DELETE_LOST_ACK"] = "true"

    result = _run_unlock(env, "release", owner)

    assert result.returncode == 0, result.stderr
    assert not (state_dir / "remote-lock").exists()
    assert not local_lock.exists()
    assert "remote-secret" not in result.stdout + result.stderr


@pytest.mark.unit
def test_safe_unlock_retry_clears_local_after_unreadable_delete_ack(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    owner = "c" * 40
    (state_dir / "remote-lock").write_text(owner)
    local_lock = Path(env["TMPDIR"]) / "tradingagents-tradagent.deploy.lock"
    local_lock.mkdir()
    (local_lock / "owner").write_text(f"pid=99999999 revision={REVISION}\n")
    env["FAKE_LOCK_POST_DELETE_UNAVAILABLE_ONCE"] = "true"

    ambiguous = _run_unlock(env, "release", owner)
    assert ambiguous.returncode == 75
    assert "release is ambiguous" in ambiguous.stderr
    assert local_lock.exists()
    reconciled = _run_unlock(env, "release", owner)
    assert reconciled.returncode == 0, reconciled.stderr
    assert "already absent" in reconciled.stdout
    assert not local_lock.exists()
    assert "remote-secret" not in ambiguous.stdout + ambiguous.stderr


@pytest.mark.unit
def test_safe_unlock_refuses_live_local_owner_and_preserves_remote(fake_deploy_env):
    env, state_dir = fake_deploy_env
    owner = "c" * 40
    (state_dir / "remote-lock").write_text(owner)
    local_lock = Path(env["TMPDIR"]) / "tradingagents-tradagent.deploy.lock"
    local_lock.mkdir()
    (local_lock / "owner").write_text(f"pid={os.getpid()} revision={REVISION}\n")

    result = _run_unlock(env, "release", owner)

    assert result.returncode == 75
    assert "PID is still alive" in result.stderr
    assert (state_dir / "remote-lock").read_text() == owner
    assert local_lock.exists()
    assert _lock_pushes(state_dir) == []


@pytest.mark.unit
def test_safe_unlock_disables_shell_and_git_tracing(fake_deploy_env):
    env, state_dir = fake_deploy_env
    trace_target = state_dir / "unlock-trace.json"
    canary = "unlock-secret-canary-never-render"
    env.update({
        "FAKE_REQUIRE_GIT_TRACE_DISABLED": "true",
        "GIT_TRACE": str(trace_target),
        "GIT_TRACE2": str(trace_target),
        "GIT_TRACE2_EVENT": str(trace_target),
        "GIT_TRACE2_PERF": str(trace_target),
        "UNRELATED_SECRET": canary,
    })

    result = _run_unlock(env, "inspect", xtrace=True)

    assert result.returncode == 0, result.stderr
    assert not trace_target.exists()
    assert canary not in result.stdout + result.stderr
