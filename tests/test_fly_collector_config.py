"""Keep the private Fly collector wired to its release and health contracts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLY_CONFIG = ROOT / "fly.toml"
DOCKERFILE = ROOT / "Dockerfile.poller"
DOCKERIGNORE = ROOT / ".dockerignore"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_collector.sh"
ROLLBACK_HELPER = ROOT / "scripts" / "fenced_machine_rollback.py"
PYPROJECT = ROOT / "pyproject.toml"


def _table(text: str, name: str) -> str:
    """Return one simple TOML table body without adding a Python 3.10 parser dep."""
    match = re.search(
        rf"(?ms)^\[{re.escape(name)}\]\s*$\n(?P<body>.*?)(?=^\[|\Z)", text
    )
    assert match is not None, f"missing [{name}]"
    return match.group("body")


def _array_table(text: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^\[\[{re.escape(name)}\]\]\s*$\n(?P<body>.*?)(?=^\[|\Z)", text
    )
    assert match is not None, f"missing [[{name}]]"
    return match.group("body")


def _quoted(body: str, key: str) -> str:
    match = re.search(rf'(?m)^\s*{re.escape(key)}\s*=\s*"([^"]*)"\s*$', body)
    assert match is not None, f"missing quoted key {key}"
    return match.group(1)


def _integer(body: str, key: str) -> int:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*(\d+)\s*$", body)
    assert match is not None, f"missing integer key {key}"
    return int(match.group(1))


@pytest.mark.unit
def test_fly_release_preflight_and_private_health_contract():
    text = FLY_CONFIG.read_text(encoding="utf-8")

    assert _quoted(_table(text, "processes"), "app") == "--global-only"
    deploy = _table(text, "deploy")
    assert _quoted(deploy, "release_command") == "--global-only --preflight"
    assert _quoted(deploy, "release_command_timeout") == "2m"
    assert _quoted(deploy, "strategy") == "immediate"

    env = _table(text, "env")
    assert _quoted(env, "MEDIA_REQUIRE_ALERT_WEBHOOK") == "true"
    health_port = int(_quoted(env, "MEDIA_HEALTH_PORT"))
    health = _table(text, "checks.collector_health")
    assert _quoted(health, "type") == "http"
    assert _integer(health, "port") == health_port
    assert _quoted(health, "method") == "get"
    assert _quoted(health, "path") == "/healthz"
    assert _quoted(health, "interval") == "60s"
    assert _quoted(health, "timeout") == "10s"
    assert _quoted(health, "grace_period") == "5m"
    assert 'processes = ["app"]' in health

    # A top-level Fly check remains private only while no public service table
    # exposes its port.
    assert re.search(r"(?m)^\[http_service(?:\.|\])", text) is None
    assert re.search(r"(?m)^\[\[services(?:\.|\])", text) is None


@pytest.mark.unit
def test_fly_worker_restart_and_image_entrypoint_contract():
    config = FLY_CONFIG.read_text(encoding="utf-8")
    restart = _array_table(config, "restart")
    assert _quoted(restart, "policy") == "always"
    # Fly's retry count applies to on-failure, not the always-on worker policy.
    assert re.search(r"(?m)^\s*retries\s*=", restart) is None
    assert 'processes = ["app"]' in restart

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["tradingagents-poller"]' in dockerfile
    assert (
        'tradingagents-poller = "tradingagents.poller:_main_entrypoint"'
        in PYPROJECT.read_text(encoding="utf-8")
    )
    assert 'LABEL org.opencontainers.image.revision="${GIT_REVISION}"' in dockerfile
    assert 'ENV GIT_REVISION="${GIT_REVISION}"' in dockerfile
    assert "/opt/tradingagents/REVISION" in dockerfile
    assert 'ARG GIT_REVISION=""' not in dockerfile
    assert "if [ -n \"$GIT_REVISION\" ]" not in dockerfile

    deploy_script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert DEPLOY_SCRIPT.stat().st_mode & 0o111
    assert "git status --porcelain" in deploy_script
    assert '--build-arg "GIT_REVISION=${revision}"' in deploy_script
    assert '--image-label "git-${revision}"' in deploy_script
    assert "collector_health" in deploy_script
    assert "fly config save" in deploy_script
    assert '-c "$previous_config"' in deploy_script
    assert 'scripts/fenced_machine_rollback.py' in deploy_script
    assert '--baseline-image "$previous_image"' in deploy_script
    assert '--baseline-digest "$previous_digest"' in deploy_script
    assert '--baseline-config-fingerprint "$previous_config_fingerprint"' in deploy_script
    rollback_helper = ROLLBACK_HELPER.read_text(encoding="utf-8")
    assert '"current_version": args.expected_instance' in rollback_helper
    assert 'headers["fly-machine-lease-nonce"] = lease_nonce' in rollback_helper
    assert "_validate_restored_machine" in rollback_helper


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
    assert "COPY constraints-poller.txt pyproject.toml README.md ./" in dockerfile
    assert "COPY tradingagents ./tradingagents" in dockerfile
    assert "COPY cli ./cli" in dockerfile
