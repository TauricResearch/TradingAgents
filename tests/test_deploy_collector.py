"""Behavioral tests for the collector's transactional Fly deploy wrapper."""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import shlex
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
if args[:3] == ["remote", "get-url", "--all"]:
    if os.environ.get("FAKE_TARGET_MULTIPLE_FETCHURLS") == "true":
        print("https://github.com/example/TradingAgents.git")
        print("https://github.com/attacker/TradingAgents.git")
    else:
        print(os.environ.get(
            "FAKE_TARGET_FETCH_URL",
            "https://github.com/example/TradingAgents.git",
        ))
    raise SystemExit(0)
if args[:3] == ["remote", "get-url", "--push"]:
    if os.environ.get("FAKE_LOCK_REMOTE_UNAVAILABLE") == "true":
        print(
            "fatal: https://user:remote-secret@example.invalid/repo.git",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if os.environ.get("FAKE_LOCK_MULTIPLE_PUSHURLS") == "true":
        print("https://github.com/example/TradingAgents.git")
        print("https://github.com/attacker/TradingAgents.git")
    else:
        print(os.environ.get(
            "FAKE_LOCK_REMOTE_URL",
            "https://github.com/example/TradingAgents.git",
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


FAKE_FLY = r"""#!/usr/bin/env python3
import json
import os
import pathlib
import shlex
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

def hang_until_bounded_command_terminates(label):
    def record_termination(_signum, _frame):
        (state_dir / "bounded-child-terminated").write_text(label)
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, record_termination)
    time.sleep(30)

def value(flag):
    return args[args.index(flag) + 1]

def machine(kind):
    if kind in {"previous", "previous-mutated-config"}:
        machine_id = "machine-old"
        rolled_back = (state_dir / "rollback-helper-calls.jsonl").exists()
        instance_id = "instance-rollback-038" if rolled_back else "instance-old-000"
        image = (
            "registry.fly.io/tradagent:"
            "deployment-01KZAD8T2KXJJJXAM2JJW8E447"
        )
        if scenario == "invalid_baseline_image":
            image = "registry.fly.io/tradagent:latest"
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
        restart = (
            {"policy": "always"}
            if scenario == "nonlegacy_deployment_baseline"
            else {"policy": "on-failure", "max_retries": 10}
        )
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
    if kind in {"previous", "previous-mutated-config"} and rolled_back:
        metadata.update({
            "tradingagents_fenced_rollback_from_release_version": "36",
            "tradingagents_fenced_rollback_to_release_version": "33",
        })
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
    if scenario == "baseline_status_malformed" and phase == "previous":
        print('{"Machines": [')
        raise SystemExit(0)
    if scenario == "baseline_status_deep_json" and phase == "previous":
        print('{"Machines":' + "[" * 2000 + "0" + "]" * 2000 + "}")
        raise SystemExit(0)
    if scenario in {
        "baseline_status_null_byte", "baseline_status_unpaired_surrogate",
    } and phase == "previous":
        unsafe = machine("previous")
        unsafe["id"] = (
            "machine\0old"
            if scenario == "baseline_status_null_byte"
            else "machine\ud800old"
        )
        print(json.dumps({"Machines": [unsafe]}))
        raise SystemExit(0)
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
    if phase == "target" and scenario in {
        "target_absent_once", "target_starting_once", "target_created_once",
        "target_pending_created", "target_started_incomplete_once",
        "target_starting_forever", "target_starting_tuple_change",
        "target_launch_failed", "target_handoff_sequence", "target_malformed_once",
        "foreign_starting", "foreign_same_commit_starting",
        "changed_machine_id_starting", "multiple_starting",
    }:
        counter_path = state_dir / "transition-status-count"
        count = int(counter_path.read_text()) if counter_path.exists() else 0
        counter_path.write_text(str(count + 1))
        if count == 0 and scenario == "target_absent_once":
            machines = []
        elif count == 0 and scenario == "target_starting_once":
            machines[0]["state"] = "starting"
        elif count == 0 and scenario == "target_created_once":
            machines[0]["state"] = "created"
        elif scenario == "target_pending_created" and count < 2:
            machines[0]["state"] = "pending" if count == 0 else "created"
        elif count == 0 and scenario == "target_started_incomplete_once":
            machines[0]["image_ref"] = {}
        elif scenario == "target_starting_forever":
            machines[0]["state"] = "starting"
        elif scenario == "target_starting_tuple_change":
            machines[0]["state"] = "starting" if count == 0 else "started"
            if count > 0:
                machines[0]["instance_id"] = "instance-changed-001"
        elif scenario == "target_launch_failed":
            machines[0]["state"] = "launch_failed"
        elif scenario == "target_handoff_sequence":
            if count < 2:
                machines = [machine("previous")]
                machines[0]["state"] = "stopping" if count == 0 else "stopped"
            elif count == 2:
                machines = []
            elif count < 5:
                machines[0]["state"] = "created" if count == 3 else "starting"
        elif count == 0 and scenario == "target_malformed_once":
            print('{"Machines": [')
            raise SystemExit(0)
        elif scenario == "foreign_starting":
            machines = [machine("foreign")]
            machines[0]["state"] = "starting"
        elif scenario == "foreign_same_commit_starting":
            machines = [machine("foreign-same-commit")]
            machines[0]["state"] = "starting"
        elif scenario == "changed_machine_id_starting":
            machines[0]["id"] = "machine-changed"
            machines[0]["state"] = "starting"
        elif scenario == "multiple_starting":
            machines = [machine("target"), machine("previous")]
            for item in machines:
                item["state"] = "starting"
    if phase == "previous" and scenario in {
        "baseline_empty_before_deploy", "baseline_starting_before_deploy",
    }:
        counter_path = state_dir / "baseline-transition-status-count"
        count = int(counter_path.read_text()) if counter_path.exists() else 0
        counter_path.write_text(str(count + 1))
        if count >= 2:
            if scenario == "baseline_empty_before_deploy":
                machines = []
            else:
                machines[0]["state"] = "starting"
    rolled_back = (
        phase == "previous"
        and (state_dir / "rollback-helper-calls.jsonl").exists()
    )
    if rolled_back and scenario == "legacy_status_hang":
        hang_until_bounded_command_terminates(scenario)
    if rolled_back and scenario in {"legacy_status_gap", "legacy_tuple_change"}:
        counter_path = state_dir / "legacy-rollback-status-count"
        count = int(counter_path.read_text()) if counter_path.exists() else 0
        counter_path.write_text(str(count + 1))
        if scenario == "legacy_status_gap" and count == 1:
            machines = []
        elif scenario == "legacy_tuple_change" and count > 0:
            machines[0]["instance_id"] = "instance-rollback-039"
    print(json.dumps({"Machines": machines}))
    raise SystemExit(0)
if args and args[0] == "releases":
    if scenario == "release_history_unavailable":
        raise SystemExit(1)
    if scenario == "release_history_malformed":
        print(json.dumps({"releases": "not-an-authenticated-list"}))
        raise SystemExit(0)
    if scenario == "release_history_invalid_json":
        print('[{"Version":')
        raise SystemExit(0)
    if scenario == "release_history_huge_integer":
        print('[{"Version":' + "9" * 5000 + ',"Status":"complete"}]')
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
    build_arguments = [
        args[index + 1]
        for index, argument in enumerate(args[:-1])
        if argument == "--build-arg"
    ]
    build_values = dict(argument.split("=", 1) for argument in build_arguments)
    deployment_nonce = build_values.get("COLLECTOR_DEPLOYMENT_NONCE", "")
    if (
        len(deployment_nonce) != 32
        or any(character not in "0123456789abcdef" for character in deployment_nonce)
        or image_label != f"git-{revision}-{deployment_nonce}"
    ):
        raise SystemExit(2)
    (state_dir / "deployment-nonce").write_text(deployment_nonce)
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
    if scenario in {
        "deploy_failure_changed", "legacy_deploy_failure_changed",
        "legacy_probe_failure", "legacy_probe_hang", "legacy_status_hang",
        "legacy_status_gap", "legacy_tuple_change",
        "nonlegacy_deployment_baseline",
    }:
        raise SystemExit(1)
    raise SystemExit(0)
if args[:2] == ["checks", "list"]:
    if scenario == "health_checks_malformed":
        print('{"machine-old": [')
        raise SystemExit(0)
    baseline_status = (
        "critical"
        if scenario in {
            "baseline_unhealthy", "legacy_baseline_health_timeout",
            "legacy_deploy_failure_changed", "legacy_probe_failure",
            "legacy_probe_hang", "legacy_probe_preflight_failure",
            "legacy_status_gap", "legacy_status_hang", "legacy_tuple_change",
            "nonlegacy_deployment_baseline",
        }
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
    if "tradingagents.collector_health" in command:
        probe_count_path = state_dir / "readiness-probe-count"
        probe_count = (
            int(probe_count_path.read_text())
            if probe_count_path.exists()
            else 0
        )
        probe_count_path.write_text(str(probe_count + 1))
        command_arguments = shlex.split(command)
        expected_nonce = command_arguments[
            command_arguments.index("--expected-deployment-nonce") + 1
        ]
        runtime_nonce = (state_dir / "deployment-nonce").read_text()
        if scenario == "same_revision_successor_stale_status" and probe_count > 0:
            runtime_nonce = "f" * 32
        if expected_nonce != runtime_nonce:
            raise SystemExit(1)
        if scenario == "signal":
            deploy_pid = int(subprocess.check_output(
                ["ps", "-o", "ppid=", "-p", str(os.getppid())],
                text=True,
            ).strip())
            os.kill(deploy_pid, signal.SIGTERM)
            raise SystemExit(143)
        if scenario in {"revision_mismatch", "stale_cached_check"}:
            raise SystemExit(1)
        if scenario == "final_readiness_failure" and probe_count > 0:
            raise SystemExit(1)
    if "poller:last_success_utc" in command:
        probe_count_path = state_dir / "legacy-probe-count"
        probe_count = (
            int(probe_count_path.read_text())
            if probe_count_path.exists()
            else 0
        )
        probe_count_path.write_text(str(probe_count + 1))
        if scenario == "legacy_probe_preflight_failure" or (
            scenario == "legacy_probe_failure" and probe_count > 0
        ):
            raise SystemExit(1)
        if scenario == "legacy_probe_hang" and probe_count > 0:
            hang_until_bounded_command_terminates(scenario)
    raise SystemExit(0)

print("unexpected fake fly invocation", args, file=sys.stderr)
raise SystemExit(2)
"""


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
    fake_python.write_text(
        textwrap.dedent(f"""\
        #!{sys.executable}
        import json
        import os
        import pathlib
        import sys

        args = sys.argv[1:]
        state_dir = pathlib.Path(os.environ["FAKE_STATE_DIR"])
        if args and args[0] == "-" and os.environ.get(
            "FAKE_RUNTIME_IDENTITY_FAILURE"
        ) == "true":
            sys.stdin.read()
            raise SystemExit(1)
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
    """),
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "TMPDIR": str(tmp_path),
        "FAKE_STATE_DIR": str(state_dir),
        "FAKE_REVISION": REVISION,
        "REAL_PYTHON": sys.executable,
        "COLLECTOR_HEALTH_TIMEOUT_SECONDS": "3",
        "COLLECTOR_HEALTH_POLL_SECONDS": "1",
        "COLLECTOR_ROLLBACK_TIMEOUT_SECONDS": "3",
        "COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE": "false",
    }
    return env, state_dir


def _run(env, *, app="tradagent", timeout=10):
    return subprocess.run(
        [str(DEPLOY), app],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
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
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


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
def test_success_is_bound_to_the_target_process_incarnation(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_HEALTH_TIMEOUT_SECONDS"] = "3"

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert f"runtime-ready at {REVISION} on Machine machine-old" in result.stdout
    deploys = _deploy_calls(state_dir)
    assert len(deploys) == 1
    assert deploys[0][deploys[0].index("--dockerfile") + 1] == "Dockerfile.poller"
    image_label = deploys[0][deploys[0].index("--image-label") + 1]
    assert re.fullmatch(rf"git-{REVISION}-[0-9a-f]{{32}}", image_label)
    deployment_nonce = image_label.rsplit("-", 1)[1]
    build_arguments = [
        deploys[0][index + 1]
        for index, argument in enumerate(deploys[0][:-1])
        if argument == "--build-arg"
    ]
    assert build_arguments == [
        f"GIT_REVISION={REVISION}",
        f"COLLECTOR_DEPLOYMENT_NONCE={deployment_nonce}",
    ]
    readiness_calls = [
        call
        for call in _calls(state_dir)
        if call[:2] == ["ssh", "console"]
        and "tradingagents.collector_health" in call[call.index("-C") + 1]
    ]
    assert len(readiness_calls) == 2
    for call in readiness_calls:
        assert call[call.index("--machine") + 1] == "machine-old"
        command = shlex.split(call[call.index("-C") + 1])
        assert command == [
            "python",
            "-m",
            "tradingagents.collector_health",
            "--expected-build-revision",
            REVISION,
            "--expected-machine-id",
            "machine-old",
            "--expected-deployment-nonce",
            deployment_nonce,
        ]
    assert not any("--test-alert" in argument for call in _calls(state_dir) for argument in call)
    assert _target_remote_reads(state_dir) == [
        [
            "ls-remote",
            "--exit-code",
            "--refs",
            "https://github.com/example/TradingAgents.git",
            "refs/heads/main",
        ],
        [
            "ls-remote",
            "--exit-code",
            "--refs",
            "https://github.com/example/TradingAgents.git",
            "refs/heads/main",
        ],
    ]
    lock_ref = "refs/heads/tradingagents-deploy-lock/tradagent"
    lock_commit = "c" * 40
    lock_url = "https://github.com/example/TradingAgents.git"
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
@pytest.mark.parametrize(
    "scenario",
    [
        "target_absent_once",
        "target_starting_once",
        "target_created_once",
        "target_pending_created",
        "target_started_incomplete_once",
    ],
)
def test_authenticated_fly_handoff_waits_for_a_started_target(
    scenario,
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario
    env["COLLECTOR_HEALTH_TIMEOUT_SECONDS"] = "4"

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert f"runtime-ready at {REVISION} on Machine machine-old" in result.stdout
    assert "superseded" not in result.stderr
    assert _rollback_helper_calls(state_dir) == []
    assert not (state_dir / "remote-lock").exists()


@pytest.mark.unit
def test_previous_stop_and_target_start_handoff_authenticates_final_target(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "target_handoff_sequence"
    # The assertion is the observed state sequence, not a scheduler-sensitive
    # race against the configured production deadline.
    env["COLLECTOR_HEALTH_TIMEOUT_SECONDS"] = "20"

    result = _run(env, timeout=30)

    assert result.returncode == 0, result.stderr
    assert f"runtime-ready at {REVISION} on Machine machine-old" in result.stdout
    assert "superseded" not in result.stderr
    assert _rollback_helper_calls(state_dir) == []
    assert not (state_dir / "remote-lock").exists()
    assert int((state_dir / "transition-status-count").read_text()) >= 6


@pytest.mark.unit
def test_persistent_handoff_never_rolls_back_and_preserves_remote_lock(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "target_starting_forever"
    env["COLLECTOR_HEALTH_TIMEOUT_SECONDS"] = "2"

    result = _run(env)

    assert result.returncode == 1
    assert "readiness and revision did not pass within 2s" in result.stderr
    assert "handoff is not authenticated as a started release" in result.stderr
    assert "superseded" not in result.stderr
    assert _rollback_helper_calls(state_dir) == []
    assert (state_dir / "remote-lock").read_text() == "c" * 40


@pytest.mark.unit
def test_transitional_target_tuple_change_is_supersession(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "target_starting_tuple_change"
    env["COLLECTOR_HEALTH_TIMEOUT_SECONDS"] = "4"

    result = _run(env)

    assert result.returncode == 75
    assert "superseded before verification" in result.stderr
    assert _rollback_helper_calls(state_dir) == []
    assert (state_dir / "remote-lock").read_text() == "c" * 40


@pytest.mark.unit
def test_terminal_candidate_never_rolls_back_and_preserves_remote_lock(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "target_launch_failed"
    env["COLLECTOR_HEALTH_TIMEOUT_SECONDS"] = "4"

    result = _run(env)

    assert result.returncode == 1
    assert "candidate entered a terminal failure state" in result.stderr
    assert _rollback_helper_calls(state_dir) == []
    assert (state_dir / "remote-lock").read_text() == "c" * 40


@pytest.mark.unit
@pytest.mark.parametrize(
    "scenario",
    [
        "foreign_starting",
        "foreign_same_commit_starting",
        "changed_machine_id_starting",
        "multiple_starting",
    ],
)
def test_foreign_nonstarted_topology_is_immediate_supersession(
    scenario,
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario
    env["COLLECTOR_HEALTH_TIMEOUT_SECONDS"] = "4"

    result = _run(env)

    assert result.returncode == 75
    assert "superseded before verification" in result.stderr
    assert _rollback_helper_calls(state_dir) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "scenario",
    ["baseline_empty_before_deploy", "baseline_starting_before_deploy"],
)
def test_predeploy_status_remains_strict_and_mutation_free(
    scenario,
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario

    result = _run(env)

    assert result.returncode == 75
    assert "changed after baseline verification" in result.stderr
    assert _deploy_calls(state_dir) == []
    assert _rollback_helper_calls(state_dir) == []
    assert not (state_dir / "remote-lock").exists()


@pytest.mark.unit
def test_malformed_handoff_status_is_silent_and_retryable(fake_deploy_env):
    env, _state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "target_malformed_once"
    env["COLLECTOR_HEALTH_TIMEOUT_SECONDS"] = "4"

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stdout + result.stderr


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scenario", "message"),
    [
        ("baseline_status_malformed", "exactly one started app Machine"),
        ("baseline_status_deep_json", "exactly one started app Machine"),
        ("baseline_status_null_byte", "exactly one started app Machine"),
        ("baseline_status_unpaired_surrogate", "exactly one started app Machine"),
        ("health_checks_malformed", "passing baseline collector_health check"),
    ],
)
def test_malformed_fly_preflight_output_has_one_contextual_error(
    scenario,
    message,
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario

    result = _run(env)

    assert result.returncode == 69
    assert message in result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    assert "ignored null byte" not in result.stdout + result.stderr
    assert "UnicodeEncodeError" not in result.stdout + result.stderr
    assert _deploy_calls(state_dir) == []


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
    env["COLLECTOR_ROLLBACK_TIMEOUT_SECONDS"] = "4"

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
        ":deployment-01KZAD8T2KXJJJXAM2JJW8E447"
    )
    assert helper[helper.index("--baseline-digest") + 1] == "sha256:" + "1" * 64
    assert helper[helper.index("--baseline-release") + 1] == "release-old"
    assert re.fullmatch(
        r"[0-9a-f]{64}",
        helper[helper.index("--baseline-config-fingerprint") + 1],
    )
    assert "--allow-legacy-baseline-on-failure" not in helper
    assert helper[helper.index("--previous-status") + 1].endswith("status.previous.json")
    assert "test-fly-token-never-render" not in json.dumps(helper_calls)


@pytest.mark.unit
def test_one_time_legacy_rollback_requires_stable_runtime_probes(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "legacy_deploy_failure_changed"
    env["COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE"] = "true"
    env["COLLECTOR_ROLLBACK_TIMEOUT_SECONDS"] = "4"

    result = _run(env)

    assert result.returncode == 1
    assert "previous collector image and configuration restored" in result.stdout
    helper = _rollback_helper_calls(state_dir)[0]
    assert helper.count("--allow-legacy-baseline-on-failure") == 1
    probe_calls = [
        call
        for call in _calls(state_dir)
        if call[:2] == ["ssh", "console"]
        and "poller:last_success_utc" in call[call.index("-C") + 1]
    ]
    assert len(probe_calls) == 3
    assert not (state_dir / "remote-lock").exists()


@pytest.mark.unit
def test_break_glass_flag_does_not_unpin_a_nonlegacy_deployment_baseline(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "nonlegacy_deployment_baseline"
    env["COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE"] = "true"
    env["COLLECTOR_ROLLBACK_TIMEOUT_SECONDS"] = "4"

    result = _run(env)

    assert result.returncode == 1
    assert "previous collector image and configuration restored" in result.stdout
    helper = _rollback_helper_calls(state_dir)[0]
    assert "--allow-legacy-baseline-on-failure" not in helper
    assert not any(
        "poller:last_success_utc" in call[call.index("-C") + 1]
        for call in _calls(state_dir)
        if call[:2] == ["ssh", "console"]
    )
    assert not (state_dir / "remote-lock").exists()


@pytest.mark.unit
@pytest.mark.parametrize("scenario", ["legacy_status_gap", "legacy_tuple_change"])
def test_legacy_rollback_requires_consecutive_bound_observations(
    scenario,
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario
    env["COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE"] = "true"
    env["COLLECTOR_ROLLBACK_TIMEOUT_SECONDS"] = "6"

    result = _run(env)

    assert result.returncode == 1
    assert "previous collector image and configuration restored" in result.stdout
    probe_calls = [
        call
        for call in _calls(state_dir)
        if call[:2] == ["ssh", "console"]
        and "poller:last_success_utc" in call[call.index("-C") + 1]
    ]
    # One pre-mutation probe plus three post-rollback probes. A status gap
    # resets stability, and an instance change starts a new bound observation.
    assert len(probe_calls) == 4
    assert not (state_dir / "remote-lock").exists()


@pytest.mark.unit
def test_failed_legacy_runtime_probe_preserves_remote_lock(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "legacy_probe_failure"
    env["COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE"] = "true"
    env["COLLECTOR_ROLLBACK_TIMEOUT_SECONDS"] = "3"

    result = _run(env)

    assert result.returncode == 1
    assert "was not restored" in result.stderr
    assert (state_dir / "remote-lock").read_text() == "c" * 40


@pytest.mark.unit
@pytest.mark.parametrize("scenario", ["legacy_probe_hang", "legacy_status_hang"])
def test_hung_legacy_rollback_observation_is_bounded_and_preserves_lock(
    scenario,
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario
    env["COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE"] = "true"
    env["COLLECTOR_ROLLBACK_TIMEOUT_SECONDS"] = "3"

    result = _run(env)

    assert result.returncode == 1
    assert (state_dir / "bounded-child-terminated").read_text() == scenario
    assert "was not restored" in result.stderr
    assert (state_dir / "remote-lock").read_text() == "c" * 40


@pytest.mark.unit
def test_legacy_runtime_probe_must_pass_before_fly_mutation(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "legacy_probe_preflight_failure"
    env["COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE"] = "true"

    result = _run(env)

    assert result.returncode == 69
    assert "runtime probe failed before deployment" in result.stderr
    assert _deploy_calls(state_dir) == []
    assert not (state_dir / "remote-lock").exists()


@pytest.mark.unit
def test_legacy_runtime_probe_conditions_survive_python_optimization(
    fake_deploy_env,
    tmp_path,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "legacy_probe_preflight_failure"
    env["COLLECTOR_DEPLOY_ALLOW_UNHEALTHY_BASELINE"] = "true"

    result = _run(env)

    assert result.returncode == 69
    probe_call = next(
        call
        for call in _calls(state_dir)
        if call[:2] == ["ssh", "console"]
        and "poller:last_success_utc" in call[call.index("-C") + 1]
    )
    interpreter, flag, code = shlex.split(probe_call[probe_call.index("-C") + 1])
    assert (interpreter, flag) == ("python", "-c")

    package = tmp_path / "probe" / "tradingagents"
    (package / "dataflows").mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "research_protocol.py").write_text(
        "def build_identity():\n    return 'build_' + 'a' * 24\n",
        encoding="utf-8",
    )
    (package / "dataflows" / "__init__.py").write_text("", encoding="utf-8")
    (package / "dataflows" / "media_store.py").write_text(
        textwrap.dedent(
            """\
            import os

            class Store:
                dialect = os.environ.get("PROBE_DIALECT", "postgresql")

                def get_meta(self, _key):
                    return float(os.environ.get("PROBE_HEARTBEAT", "1"))

                def close(self):
                    return None

            def open_store(*, auto_migrate):
                if auto_migrate:
                    raise RuntimeError("probe must not migrate")
                return Store()
            """
        ),
        encoding="utf-8",
    )
    probe_env = {
        **os.environ,
        "PYTHONPATH": str(tmp_path / "probe"),
        "FLY_IMAGE_REF": ("registry.fly.io/tradagent:deployment-01KZAD8T2KXJJJXAM2JJW8E447"),
        "PROBE_HEARTBEAT": "1",
    }

    def run_probe(**overrides):
        return subprocess.run(
            [sys.executable, "-O", "-c", code],
            cwd=tmp_path,
            env={**probe_env, **overrides},
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )

    assert run_probe().returncode == 0
    assert run_probe(FLY_IMAGE_REF="registry.fly.io/tradagent:wrong").returncode == 1
    assert run_probe(PROBE_HEARTBEAT="0").returncode == 1
    assert run_probe(PROBE_DIALECT="sqlite").returncode == 1


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
    while time.monotonic() < deadline and (
        not phase_path.exists() or phase_path.read_text() != "target"
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
    assert "handoff is not authenticated as a started release" in result.stderr
    assert "newer release" not in result.stderr
    assert _rollback_helper_calls(state_dir) == []
    assert (state_dir / "remote-lock").read_text() == "c" * 40


@pytest.mark.unit
@pytest.mark.parametrize("scenario", ["health_timeout", "wrong_machine_check", "revision_mismatch"])
def test_unverified_target_rolls_back(scenario, fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario
    env["COLLECTOR_ROLLBACK_TIMEOUT_SECONDS"] = "4"

    result = _run(env)

    assert result.returncode == 1
    assert len(_deploy_calls(state_dir)) == 1
    assert len(_rollback_helper_calls(state_dir)) == 1
    assert "previous collector image and configuration restored" in result.stdout


@pytest.mark.unit
def test_cached_passing_fly_check_cannot_replace_current_process_readiness(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "stale_cached_check"
    env["COLLECTOR_HEALTH_TIMEOUT_SECONDS"] = "3"

    result = _run(env)

    assert result.returncode == 1
    assert len(_deploy_calls(state_dir)) == 1
    assert (state_dir / "readiness-probe-count").exists()
    assert len(_rollback_helper_calls(state_dir)) == 1
    assert "previous collector image and configuration restored" in result.stdout


@pytest.mark.unit
def test_final_process_readiness_probe_cannot_be_replaced_by_the_first(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "final_readiness_failure"
    env["COLLECTOR_HEALTH_TIMEOUT_SECONDS"] = "3"

    result = _run(env)

    assert result.returncode == 1
    assert int((state_dir / "readiness-probe-count").read_text()) >= 2
    assert len(_rollback_helper_calls(state_dir)) == 1


@pytest.mark.unit
def test_same_revision_machine_successor_cannot_reuse_stale_status(
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "same_revision_successor_stale_status"
    env["COLLECTOR_HEALTH_TIMEOUT_SECONDS"] = "3"

    result = _run(env)

    assert result.returncode == 1
    assert "runtime-ready" not in result.stdout
    assert int((state_dir / "readiness-probe-count").read_text()) >= 2
    assert len(_rollback_helper_calls(state_dir)) == 1


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
def test_runtime_incompatible_baseline_pin_fails_before_deploy(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "invalid_baseline_image"

    result = _run(env)

    assert result.returncode == 65
    assert _deploy_calls(state_dir) == []
    assert "rollback image is incompatible" in result.stderr
    assert not (state_dir / "remote-lock").exists()


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
    assert "cannot certify it runtime-ready" in result.stderr


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
    "scenario",
    [
        "release_history_unavailable",
        "release_history_malformed",
        "release_history_invalid_json",
        "release_history_huge_integer",
    ],
)
def test_unverifiable_release_history_fails_closed_without_rollback(
    scenario,
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = scenario

    result = _run(env)

    assert result.returncode == 75
    assert len(_deploy_calls(state_dir)) == 1
    assert "candidate predecessor is not the saved baseline" in result.stderr
    assert "restoring the previous collector" not in result.stderr
    assert "Traceback" not in result.stdout + result.stderr


@pytest.mark.unit
@pytest.mark.parametrize(
    "scenario",
    ["rollback_fenced_race", "fenced_rollback_failure"],
)
def test_fenced_rollback_failure_has_no_unconditional_fallback(
    scenario,
    fake_deploy_env,
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
def test_signal_after_remote_mutation_runs_controlled_rollback(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_SCENARIO"] = "signal"
    env["COLLECTOR_HEALTH_TIMEOUT_SECONDS"] = "4"
    env["COLLECTOR_ROLLBACK_TIMEOUT_SECONDS"] = "4"

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
def test_default_lock_uses_target_remote_without_branch_tracking(fake_deploy_env):
    env, state_dir = fake_deploy_env

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert ["remote", "get-url", "--all", "origin"] in _git_calls(state_dir)
    assert ["remote", "get-url", "--push", "--all", "origin"] in _git_calls(state_dir)
    assert not any("@{" in argument for call in _git_calls(state_dir) for argument in call)


@pytest.mark.unit
def test_explicit_target_ref_replaces_origin_main(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_TARGET_REF"] = "fork/main"

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert ["remote", "get-url", "--all", "fork"] in _git_calls(state_dir)
    assert ["remote", "get-url", "--push", "--all", "fork"] in _git_calls(state_dir)


@pytest.mark.unit
def test_rollback_timeout_rejects_an_unusable_subprocess_budget(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_ROLLBACK_TIMEOUT_SECONDS"] = "2"

    result = _run(env)

    assert result.returncode == 64
    assert "must be at least 3" in result.stderr
    assert not (state_dir / "calls.jsonl").exists()
    assert not (state_dir / "remote-lock").exists()


@pytest.mark.unit
def test_runtime_image_preflight_fails_before_fly_or_remote_lock(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_RUNTIME_IDENTITY_FAILURE"] = "true"

    result = _run(env)

    assert result.returncode == 65
    assert "image tag is incompatible" in result.stderr
    assert not (state_dir / "calls.jsonl").exists()
    assert not (state_dir / "remote-lock").exists()


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
    assert ["rev-parse", "--verify", "HEAD"] in rev_parses
    assert not any(
        call[:2] == ["rev-parse", "--verify"] and call[-1] != "HEAD" for call in rev_parses
    )


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["unavailable", "malformed"])
def test_unavailable_or_malformed_remote_fails_closed_without_leaking_output(mode, fake_deploy_env):
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
    assert "runtime-ready at" in result.stdout
    assert "remote-secret" not in result.stdout + result.stderr
    assert (state_dir / "remote-lock").read_text() == "d" * 40


@pytest.mark.unit
def test_unreleased_owned_remote_lock_turns_success_into_failure(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_LOCK_CLEANUP_FAILURE"] = "true"

    result = _run(env)

    assert result.returncode == 74
    assert "runtime-ready at" in result.stdout
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
def test_divergent_explicit_lock_remote_is_rejected_before_fly(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_LOCK_REMOTE"] = "somewhere-else"

    result = _run(env)

    assert result.returncode == 64
    assert "must match the configured deployment target remote" in result.stderr
    assert _deploy_calls(state_dir) == []
    assert not any(call[:2] == ["remote", "get-url"] for call in _git_calls(state_dir))


@pytest.mark.unit
def test_matching_explicit_lock_remote_uses_the_target_namespace(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_TARGET_REF"] = "reviewed/main"
    env["COLLECTOR_DEPLOY_LOCK_REMOTE"] = "reviewed"

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert ["remote", "get-url", "--push", "--all", "reviewed"] in _git_calls(state_dir)


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
    env.update(
        {
            "FAKE_REQUIRE_GIT_TRACE_DISABLED": "true",
            "GIT_TRACE": str(trace_target),
            "GIT_TRACE2": str(trace_target),
            "GIT_TRACE2_EVENT": str(trace_target),
            "GIT_TRACE2_PERF": str(trace_target),
        }
    )

    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert not trace_target.exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    "setting",
    ["FAKE_TARGET_FETCH_URL", "FAKE_LOCK_REMOTE_URL"],
)
@pytest.mark.parametrize(
    "remote_url",
    [
        "https://token@github.com/example/TradingAgents.git",
        "https://github.com/example/TradingAgents.git?token=private",
    ],
)
def test_deploy_remote_rejects_credential_bearing_urls(
    setting,
    remote_url,
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_ALLOW_UNMERGED"] = "true"
    env[setting] = remote_url

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
def test_multiple_target_fetch_urls_fail_before_fly(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["FAKE_TARGET_MULTIPLE_FETCHURLS"] = "true"

    result = _run(env)

    assert result.returncode == 64
    assert _deploy_calls(state_dir) == []


@pytest.mark.unit
def test_target_fetch_and_push_must_not_form_a_fork_triangle(fake_deploy_env):
    env, state_dir = fake_deploy_env
    fetch_url = "https://github.com/upstream/TradingAgents.git"
    push_url = "git@github.com:contributor/TradingAgents.git"
    env["FAKE_TARGET_FETCH_URL"] = fetch_url
    env["FAKE_LOCK_REMOTE_URL"] = push_url

    result = _run(env)

    assert result.returncode == 64
    assert "must name the same GitHub repository" in result.stderr
    assert _deploy_calls(state_dir) == []
    assert fetch_url not in result.stdout + result.stderr
    assert push_url not in result.stdout + result.stderr


@pytest.mark.unit
@pytest.mark.parametrize(
    "fetch_url,push_url",
    [
        (
            "https://github.com/Example/TradingAgents.git",
            "git@github.com:example/tradingagents",
        ),
        (
            "ssh://git@github.com/EXAMPLE/TradingAgents.GIT",
            "https://github.com/example/tradingagents.git",
        ),
    ],
)
def test_equivalent_github_url_forms_share_one_lock_repository(
    fetch_url,
    push_url,
    fake_deploy_env,
):
    env, state_dir = fake_deploy_env
    env["FAKE_TARGET_FETCH_URL"] = fetch_url
    env["FAKE_LOCK_REMOTE_URL"] = push_url

    deployed = _run(env)
    inspected = _run_unlock(env, "inspect")

    assert deployed.returncode == 0, deployed.stderr
    assert inspected.returncode == 0, inspected.stderr
    assert any(push_url in call for call in _lock_pushes(state_dir))


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
        assert (
            subprocess.run(
                ["git", "for-each-ref", "--format=%(refname)"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            == ""
        )

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
def test_safe_unlock_derives_lock_remote_from_target(fake_deploy_env):
    env, state_dir = fake_deploy_env
    env["COLLECTOR_DEPLOY_TARGET_REF"] = "reviewed/main"

    result = _run_unlock(env, "inspect")

    assert result.returncode == 0, result.stderr
    assert ["remote", "get-url", "--all", "reviewed"] in _git_calls(state_dir)
    assert ["remote", "get-url", "--push", "--all", "reviewed"] in _git_calls(state_dir)


@pytest.mark.unit
def test_safe_unlock_rejects_a_lock_remote_outside_target(fake_deploy_env):
    env, state_dir = fake_deploy_env
    owner = "c" * 40
    (state_dir / "remote-lock").write_text(owner)
    env["COLLECTOR_DEPLOY_LOCK_REMOTE"] = "somewhere-else"

    result = _run_unlock(env, "inspect")

    assert result.returncode == 64
    assert "must match the configured deployment target remote" in result.stderr
    assert (state_dir / "remote-lock").read_text() == owner
    assert not any(call[:2] == ["remote", "get-url"] for call in _git_calls(state_dir))


@pytest.mark.unit
def test_safe_unlock_rejects_a_target_fetch_push_triangle(fake_deploy_env):
    env, state_dir = fake_deploy_env
    fetch_url = "https://github.com/upstream/TradingAgents.git"
    push_url = "ssh://git@github.com/contributor/TradingAgents.git"
    env["FAKE_TARGET_FETCH_URL"] = fetch_url
    env["FAKE_LOCK_REMOTE_URL"] = push_url

    result = _run_unlock(env, "inspect")

    assert result.returncode == 69
    assert "must name the same GitHub repository" in result.stderr
    assert fetch_url not in result.stdout + result.stderr
    assert push_url not in result.stdout + result.stderr


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
    env.update(
        {
            "FAKE_REQUIRE_GIT_TRACE_DISABLED": "true",
            "GIT_TRACE": str(trace_target),
            "GIT_TRACE2": str(trace_target),
            "GIT_TRACE2_EVENT": str(trace_target),
            "GIT_TRACE2_PERF": str(trace_target),
            "UNRELATED_SECRET": canary,
        }
    )

    result = _run_unlock(env, "inspect", xtrace=True)

    assert result.returncode == 0, result.stderr
    assert not trace_target.exists()
    assert canary not in result.stdout + result.stderr
