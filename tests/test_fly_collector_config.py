"""Keep the private Fly collector wired to its release and health contracts."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 CI
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
FLY_CONFIG = ROOT / "fly.toml"
DOCKERFILE = ROOT / "Dockerfile.poller"
DOCKERIGNORE = ROOT / ".dockerignore"
PYPROJECT = ROOT / "pyproject.toml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
BUILD_IMAGE = ROOT / "scripts" / "build_collector_image.sh"


def _fly_config() -> dict:
    with FLY_CONFIG.open("rb") as handle:
        return tomllib.load(handle)


@pytest.mark.unit
def test_fly_release_preflight_and_private_health_contract():
    config = _fly_config()

    assert config["processes"]["app"] == "--global-only"
    assert config["deploy"] == {
        "release_command": "--global-only --preflight",
        "release_command_timeout": "2m",
        "strategy": "immediate",
    }

    env = config["env"]
    assert env["MEDIA_REQUIRE_ALERT_WEBHOOK"] == "true"
    assert set(config["checks"]) == {"collector_health"}
    health = config["checks"]["collector_health"]
    assert health == {
        "type": "http",
        "port": int(env["MEDIA_HEALTH_PORT"]),
        "method": "get",
        "path": "/readyz",
        "interval": "60s",
        "timeout": "10s",
        "grace_period": "5m",
        "processes": ["app"],
    }

    # A top-level Fly check remains private only while no public service table
    # exposes its port.
    assert "http_service" not in config
    assert "services" not in config


@pytest.mark.unit
def test_fly_worker_restart_and_image_entrypoint_contract():
    config = _fly_config()

    assert config["kill_signal"] == "SIGTERM"
    assert config["kill_timeout"] == "300s"
    assert config["build"]["dockerfile"] == "Dockerfile.poller"
    assert config["restart"] == [{"policy": "always", "processes": ["app"]}]
    # Fly's retry count applies to on-failure, not the always-on worker policy.
    assert "retries" not in config["restart"][0]

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["tradingagents-poller"]' in dockerfile
    with PYPROJECT.open("rb") as handle:
        project = tomllib.load(handle)
    assert project["project"]["scripts"]["tradingagents-poller"] == (
        "cli.entrypoints:poller"
    )
    assert 'LABEL org.opencontainers.image.revision="${GIT_REVISION}"' in dockerfile
    assert 'ENV GIT_REVISION="${GIT_REVISION}"' in dockerfile
    assert "ARG COLLECTOR_DEPLOYMENT_NONCE" in dockerfile
    assert 'ENV COLLECTOR_DEPLOYMENT_NONCE="${COLLECTOR_DEPLOYMENT_NONCE}"' in dockerfile
    assert "'^[0-9a-f]{32}$'" in dockerfile
    assert "/opt/tradingagents/REVISION" in dockerfile
    assert 'ARG GIT_REVISION=""' not in dockerfile
    assert 'if [ -n "$GIT_REVISION" ]' not in dockerfile


@pytest.mark.unit
def test_poller_image_context_is_deny_by_default_and_copy_is_allowlisted():
    dockerignore = DOCKERIGNORE.read_text(encoding="utf-8")
    meaningful_patterns = [
        line.strip()
        for line in dockerignore.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert meaningful_patterns[0] == "**"
    assert "!Dockerfile.poller" in meaningful_patterns
    assert "!constraints-poller.txt" in meaningful_patterns
    assert "!pyproject.toml" in meaningful_patterns
    assert "!README.md" in meaningful_patterns
    assert "!tradingagents/**/*.py" in meaningful_patterns
    assert "!cli/**/*.py" in meaningful_patterns
    assert "!cli/static/welcome.txt" in meaningful_patterns
    assert all(
        not pattern.startswith("!")
        or pattern
        in {
            "!Dockerfile.poller",
            "!constraints-poller.txt",
            "!pyproject.toml",
            "!README.md",
            "!tradingagents/**/*.py",
            "!cli/**/*.py",
            "!cli/static/welcome.txt",
        }
        for pattern in meaningful_patterns
    )

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY . ." not in dockerfile
    assert "COPY constraints-poller.txt ./" in dockerfile
    assert "COPY pyproject.toml README.md ./" in dockerfile
    assert "COPY tradingagents ./tradingagents" in dockerfile
    assert "COPY cli ./cli" in dockerfile
    assert (
        dockerfile.index("pip install --no-cache-dir --require-hashes")
        < dockerfile.index("COPY tradingagents ./tradingagents")
        < dockerfile.index("pip install --no-cache-dir --no-deps")
    )


@pytest.mark.unit
def test_ci_collector_image_builder_passes_exact_identity(tmp_path):
    calls = tmp_path / "docker-args"
    github_env = tmp_path / "github-env"
    fake_docker = tmp_path / "docker"
    fake_docker.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$DOCKER_CALLS\"\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    revision = "a" * 40
    nonce = "b" * 32

    subprocess.run(
        [str(BUILD_IMAGE), "collector:test"],
        cwd=ROOT,
        env={
            **os.environ,
            "DOCKER_BIN": str(fake_docker),
            "DOCKER_CALLS": str(calls),
            "GITHUB_ENV": str(github_env),
            "GIT_REVISION": revision,
            "COLLECTOR_DEPLOYMENT_NONCE": nonce,
        },
        check=True,
    )

    assert calls.read_text(encoding="utf-8").splitlines() == [
        "build",
        "--build-arg",
        f"GIT_REVISION={revision}",
        "--build-arg",
        f"COLLECTOR_DEPLOYMENT_NONCE={nonce}",
        "--file",
        "Dockerfile.poller",
        "--tag",
        "collector:test",
        ".",
    ]
    assert github_env.read_text(encoding="utf-8") == (
        f"COLLECTOR_DEPLOYMENT_NONCE={nonce}\n"
    )
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    assert workflow.count("scripts/build_collector_image.sh tradingagents-") == 2
    assert 'test "$COLLECTOR_DEPLOYMENT_NONCE" = "$EXPECTED_DEPLOYMENT_NONCE"' in workflow
