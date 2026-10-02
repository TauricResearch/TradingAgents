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
    shutil.copy2(ROOT / "scripts/report_guard.py", root / "scripts/report_guard.py")
    (root / "cli").mkdir(exist_ok=True)
    for helper in ("__init__.py", "report_fields.py"):
        shutil.copy2(ROOT / "cli" / helper, root / "cli" / helper)
    # A changed shared list must apply to every launcher without local copies.
    tickers = ["SPY", "YINN", "CUSTOM"]
    (root / "scripts/default_tickers.sh").write_text(
        "DEFAULT_TICKERS=(" + " ".join(tickers) + ")\n"
    )
    for ticker in tickers:
        report = root / "docs" / ticker / "20000101_fixture-model_20000102_030405"
        for stage in ("complete_report.md", "1_analysts/market.md", "3_trading/trader.md", "5_portfolio/decision.md"):
            path = report / stage
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Price Target: 120")
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


@pytest.mark.parametrize("token_budget", [None, "65536"])
@pytest.mark.parametrize("effort", [None, "max"])
@pytest.mark.parametrize("models,default_budget", [
    (("claude-opus-5-5", "claude-opus-5-5"), "128000"),
    (("claude-opus-5-5", "claude-sonnet-5-5"), "128000"),
    (("claude-opus-4-5", "claude-sonnet-5-5"), ""),
    (("claude-opus-5-5", "claude-haiku-4-5"), ""),
])
def test_claude_workers_receive_output_budget(tmp_path, token_budget, effort, models, default_budget):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "bin").mkdir()
    for name in ("run_missing_today_claude.sh", "report_guard.py", "default_tickers.sh"):
        shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)
    (root / "cli").mkdir(exist_ok=True)
    for helper in ("__init__.py", "report_fields.py"):
        shutil.copy2(ROOT / "cli" / helper, root / "cli" / helper)
    worker = root / "bin/uv"
    worker.write_text('''#!/bin/bash
printf '%s' "$TRADINGAGENTS_MAX_TOKENS" > "$CAPTURE"
printf '%s\\n' "$@" > "$CAPTURE.args"
report="docs/NVDA/20000101_${TRADINGAGENTS_DEEP_THINK_LLM}_20000102_030405"
mkdir -p "$report/1_analysts" "$report/3_trading" "$report/5_portfolio"
for stage in complete_report.md 1_analysts/market.md 3_trading/trader.md 5_portfolio/decision.md; do
  echo "Price Target: 120" > "$report/$stage"
done
''')
    worker.chmod(0o755)
    capture = root / "budget"
    env = {
        "PATH": str(root / "bin") + os.pathsep + os.defpath,
        "TRADINGAGENTS_MODE": "direct",
        "TRADINGAGENTS_DATE": "2000-01-01",
        "TRADINGAGENTS_DEEP_MODEL": models[0],
        "TRADINGAGENTS_QUICK_MODEL": models[1],
        "TA_LOGDIR": str(root / "logs"),
        "CAPTURE": str(capture),
    }
    if token_budget is not None:
        env["TRADINGAGENTS_MAX_TOKENS"] = token_budget
    if effort is not None:
        env["TRADINGAGENTS_OPENAI_REASONING_EFFORT"] = effort
    result = subprocess.run(
        ["bash", str(root / "scripts/run_missing_today_claude.sh"), "NVDA"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert capture.read_text() == (token_budget or default_budget)
    args = capture.with_suffix(".args").read_text().splitlines()
    assert args[args.index("--anthropic-effort") + 1] == (effort or "high")
