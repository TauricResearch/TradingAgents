"""Shared proxy/direct mode selection for the three dual-route launchers."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = {
    "claude": "TRADINGAGENTS_CLAUDE_MODE",
    "gemini": "TRADINGAGENTS_GEMINI_MODE",
    "gpt": "TRADINGAGENTS_GPT_MODE",
}


@pytest.mark.parametrize("provider", LAUNCHERS)
@pytest.mark.parametrize("shared,specific,expected", [
    (None, None, "proxy"),
    ("direct", None, "direct"),
    ("direct", "proxy", "proxy"),
    ("proxy", "direct", "direct"),
])
def test_shared_mode_and_provider_override(tmp_path, provider, shared, specific, expected):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "bin").mkdir()
    script = root / f"scripts/run_missing_today_{provider}.sh"
    shutil.copy2(ROOT / script.relative_to(root), script)

    brew = root / "bin/brew"
    brew.write_text('#!/bin/bash\necho brew >> "$CAPTURE"\n')
    brew.chmod(0o755)
    python = root / "bin/python"
    python.write_text(
        '#!/bin/bash\necho python >> "$CAPTURE"\n'
        'if [ "$2" = --key ]; then echo fixture-key; fi\n'
    )
    python.chmod(0o755)

    capture = root / "calls"
    env = {
        "PATH": str(root / "bin") + os.pathsep + os.defpath,
        "TRADINGAGENTS_PYTHON": str(python),
        "CAPTURE": str(capture),
    }
    if shared is not None:
        env["TRADINGAGENTS_MODE"] = shared
    if specific is not None:
        env[LAUNCHERS[provider]] = specific
    result = subprocess.run(
        ["bash", str(script), "--check-only"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=10,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = capture.read_text().splitlines() if capture.exists() else []
    assert ("brew" in calls) is (expected == "proxy")
    assert ("Direct" in result.stdout) is (expected == "direct")


@pytest.mark.parametrize("provider", LAUNCHERS)
def test_invalid_shared_mode_fails_before_preflight(tmp_path, provider):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    script = root / f"scripts/run_missing_today_{provider}.sh"
    shutil.copy2(ROOT / script.relative_to(root), script)
    result = subprocess.run(
        ["bash", str(script), "--check-only"], cwd=tmp_path,
        env={"PATH": os.defpath, "TRADINGAGENTS_MODE": "invalid"},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "TRADINGAGENTS_MODE must be proxy or direct" in result.stderr


@pytest.mark.parametrize("provider", LAUNCHERS)
def test_no_arguments_uses_all_shared_tickers(tmp_path, provider):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    script = root / f"scripts/run_missing_today_{provider}.sh"
    shutil.copy2(ROOT / script.relative_to(root), script)
    # A changed shared list must apply to every launcher without local copies.
    tickers = ["SPY", "YINN", "CUSTOM"]
    (root / "scripts/default_tickers.sh").write_text(
        "DEFAULT_TICKERS=(" + " ".join(tickers) + ")\n"
    )
    for ticker in tickers:
        (root / "docs" / ticker / "20000101_fixture-model_complete").mkdir(parents=True)
    result = subprocess.run(
        ["bash", str(script)], cwd=tmp_path,
        env={
            "PATH": os.defpath,
            "TRADINGAGENTS_MODE": "direct",
            "TRADINGAGENTS_PYTHON": "/usr/bin/true",
            "TRADINGAGENTS_DATE": "2000-01-01",
            "TRADINGAGENTS_DEEP_MODEL": "fixture-model",
            "TA_LOGDIR": str(root / "logs"),
        },
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Nothing to run — all 3 tickers already have" in result.stdout
    assert not result.stderr
