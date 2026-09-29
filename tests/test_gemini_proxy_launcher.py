"""Offline coverage for the native Gemini proxy launcher."""
import io
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import claude_proxy, gemini_model_probe

ROOT = Path(__file__).resolve().parents[1]


def test_gemini_catalog(monkeypatch):
    monkeypatch.setenv("CLIPROXY_API_KEY", "fixture-key")
    with patch.object(claude_proxy.urllib.request, "urlopen", return_value=io.BytesIO(
        b'{"data":[{"id":"gemini-test"}]}'
    )):
        claude_proxy.check_models("http://localhost:8317", ["gemini-test"], "gemini")
    with patch.object(claude_proxy.urllib.request, "urlopen", return_value=io.BytesIO(
        b'{"data":[]}'
    )), pytest.raises(ValueError, match="Configure Gemini credentials"):
        claude_proxy.check_models("http://localhost:8317", ["gemini-test"], "gemini")


@pytest.mark.parametrize("mode,brew_status,check_only,probe_status", [
    ("proxy", "0", True, "0"), ("proxy", "1", True, "0"),
    ("direct", "0", True, "0"), ("direct", "0", True, "1"),
    ("proxy", "0", False, "0"), ("proxy", "0", False, "1"),
    ("direct", "0", False, "0"),
])
def test_launcher(tmp_path, mode, brew_status, check_only, probe_status):
    root = tmp_path / "repo with spaces"
    (root / "scripts").mkdir(parents=True)
    (root / "bin").mkdir()
    script = root / "scripts/run_missing_today_gemini.sh"
    shutil.copy2(ROOT / "scripts/run_missing_today_gemini.sh", script)
    shutil.copy2(ROOT / "scripts/default_tickers.sh", root / "scripts/default_tickers.sh")
    programs = {
        "brew": 'echo "brew $*" >> "$CAPTURE"\nexit "$BREW_STATUS"',
        "python": 'echo python >> "$CAPTURE"\nif [ "$2" = --key ]; then echo fixture-key; elif [ "$1" = -m ]; then [ "$2" = scripts.gemini_model_probe ] && exit "$PROBE_STATUS"; else [ "$3" = gemini ]; fi',
        "uv": '''
[ "$TRADINGAGENTS_REPORTS_DIR" = "$PWD/docs" ] || exit 2
[ "$TRADINGAGENTS_LLM_PROVIDER" = google ] || exit 3
if [ "$TRADINGAGENTS_GEMINI_MODE" = proxy ]; then
  [ "$GOOGLE_API_KEY" = fixture-key ] || exit 4
  [ -z "${GEMINI_API_KEY:-}" ] || exit 9
  [ "$GOOGLE_GENAI_USE_VERTEXAI" = false ] || exit 5
  [ "$TRADINGAGENTS_LLM_BACKEND_URL" = http://127.0.0.1:8317 ] || exit 6
else
  [ "$GOOGLE_API_KEY" = direct-key ] || exit 7
  [ -z "${GEMINI_API_KEY:-}" ] || exit 10
  [ "$TRADINGAGENTS_LLM_BACKEND_URL" = https://generativelanguage.googleapis.com ] || exit 8
fi
mkdir -p docs/NVDA/20000101_gemini-test_fixture
''',
    }
    for name, body in programs.items():
        p = root / "bin" / name
        p.write_text("#!/bin/bash\n" + body + "\n")
        p.chmod(0o755)
    capture = root / "calls"
    env = {"PATH": str(root / "bin") + os.pathsep + os.defpath,
           "TRADINGAGENTS_PYTHON": str(root / "bin/python"),
           "TRADINGAGENTS_GEMINI_MODE": mode, "BREW_STATUS": brew_status,
           "PROBE_STATUS": probe_status,
           "CAPTURE": str(capture), "TRADINGAGENTS_DATE": "2000-01-01",
           "TRADINGAGENTS_DEEP_MODEL": "gemini-test", "GOOGLE_API_KEY": "direct-key",
           "GEMINI_API_KEY": "stale-key",
           "TA_LOGDIR": str(root / "logs"), "TRADINGAGENTS_REPORTS_DIR": "/.../docs"}
    result = subprocess.run(["bash", str(script), "--check-only" if check_only else "NVDA"],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
    expected_status = int(probe_status == "1" or (mode == "proxy" and brew_status == "1"))
    assert result.returncode == expected_status, result.stdout + result.stderr
    calls = capture.read_text().splitlines() if capture.exists() else []
    assert calls == (["python"] if mode == "direct" else
                     ["brew services start cliproxyapi"] +
                     ([] if brew_status == "1" else ["python", "python", "python"]))
    assert (root / "docs").exists() is (not check_only and expected_status == 0)


@pytest.mark.parametrize("mode,default_model", [
    ("proxy", "gemini-3.8-flash-high"),
    ("direct", "gemini-3.8-flash"),
])
def test_mode_default_model(tmp_path, mode, default_model):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "bin").mkdir()
    script = root / "scripts/run_missing_today_gemini.sh"
    shutil.copy2(ROOT / "scripts/run_missing_today_gemini.sh", script)
    brew = root / "bin/brew"
    brew.write_text("#!/bin/bash\nexit 0\n")
    brew.chmod(0o755)
    python = root / "bin/python"
    python.write_text(
        '#!/bin/bash\nif [ "$2" = --key ]; then echo fixture-key; '
        'elif [ "$1" = -m ]; then printf "%s\\n" "$@" > "$CAPTURE"; fi\n'
    )
    python.chmod(0o755)
    capture = root / "probe_args"
    env = {
        "PATH": str(root / "bin") + os.pathsep + os.defpath,
        "TRADINGAGENTS_PYTHON": str(python),
        "TRADINGAGENTS_GEMINI_MODE": mode,
        "CAPTURE": str(capture),
    }
    result = subprocess.run(
        ["bash", str(script), "--check-only"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert capture.read_text().splitlines()[-1] == default_model


def test_probe_reports_exhausted_quota(monkeypatch):
    monkeypatch.setattr(gemini_model_probe, "client_key", lambda: "fixture-key")
    with patch.object(gemini_model_probe.genai, "Client") as client:
        client.return_value.models.generate_content.side_effect = Exception(
            "429 {'error': {'code': 'model_cooldown', "
            "'message': 'Individual quota reached', 'reset_time': '167h55m44s'}}"
        )
        with pytest.raises(RuntimeError, match=r"upstream quota exhausted \(resets in 167h55m44s\)"):
            gemini_model_probe.probe_models("http://localhost:8317", ["gemini-test"], "high", "proxy")


def test_probe_checks_duplicate_model_once(monkeypatch):
    monkeypatch.setattr(gemini_model_probe, "client_key", lambda: "fixture-key")
    with patch.object(gemini_model_probe.genai, "Client") as client:
        gemini_model_probe.probe_models(
            "http://localhost:8317", ["gemini-test", "gemini-test"], "high", "proxy"
        )
        client.return_value.models.generate_content.assert_called_once()


def test_direct_probe_uses_google_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "direct-key")
    with patch.object(gemini_model_probe.genai, "Client") as client:
        gemini_model_probe.probe_models(
            "https://generativelanguage.googleapis.com", ["gemini-3.8-flash"], "high", "direct"
        )
        assert client.call_args.kwargs["api_key"] == "direct-key"
        config = client.return_value.models.generate_content.call_args.kwargs["config"]
        assert config.automatic_function_calling.disable is True
