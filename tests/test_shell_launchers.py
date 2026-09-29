"""Shell parsing and completion when a launcher is edited during a long run."""

import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("script", sorted((ROOT / "scripts").glob("*.sh")), ids=lambda p: p.name)
def test_shell_syntax(script):
    result = subprocess.run(["/bin/bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", [
    "run_missing_today_gpt.sh", "run_missing_today_claude.sh",
    "run_missing_today_gemini.sh", "run_all_today.sh", "publish_site.sh",
])
@pytest.mark.parametrize("worker_fails", [False, True])
def test_edit_during_worker_preserves_completion(tmp_path, name, worker_fails):
    root = tmp_path / "repo with spaces"
    (root / "scripts").mkdir(parents=True)
    (root / "bin").mkdir()
    (root / ".venv/bin").mkdir(parents=True)
    script = root / "scripts" / name
    shutil.copy2(ROOT / "scripts" / name, script)
    shutil.copy2(ROOT / "scripts/default_tickers.sh", root / "scripts/default_tickers.sh")
    original = script.read_text()

    worker = root / "worker.py"
    worker.write_text('''import os, sys, time
from pathlib import Path
root = Path(os.environ["SMOKE_ROOT"])
(root / "ready").touch()
deadline = time.monotonic() + 10
while not (root / "release").exists():
    if time.monotonic() > deadline:
        raise SystemExit("test did not release worker")
    time.sleep(0.01)
if os.environ["SMOKE_FAIL"] == "1":
    raise SystemExit(17)
if sys.argv[1].endswith("build_publish_site.py"):
    raise SystemExit(0)
value = lambda flag: sys.argv[sys.argv.index(flag) + 1]
slug = value("--deep-model").translate(str.maketrans({"/": "-", ":": "-", ".": "-"}))
report = Path(os.environ["TRADINGAGENTS_REPORTS_DIR"]) / value("--ticker") / (value("--date").replace("-", "") + "_" + slug + "_fixture")
report.mkdir(parents=True)
''')
    wrapper = f'#!/bin/bash\nexec {shlex.quote(sys.executable)} {shlex.quote(str(worker))} "$@"\n'
    programs = {
        "bin/uv": wrapper,
        ".venv/bin/python": wrapper,
        "bin/probe-python": "#!/bin/bash\nexit 0\n",
        "bin/git": "#!/bin/bash\necho fixture-commit\n",
    }
    for path, body in programs.items():
        program = root / path
        program.write_text(body)
        program.chmod(0o755)

    env = {
        "PATH": str(root / "bin") + os.pathsep + os.defpath,
        "TRADINGAGENTS_MODE": "direct",
        "TRADINGAGENTS_PYTHON": str(root / "bin/probe-python"),
        "TRADINGAGENTS_DATE": "2000-01-01",
        "TA_LOGDIR": str(root / "logs"),
        "SMOKE_ROOT": str(root),
        "SMOKE_FAIL": str(int(worker_fails)),
    }
    args = ["--dry-run"] if name == "publish_site.sh" else ["NVDA"]
    process = subprocess.Popen(
        ["/bin/bash", str(script), *args], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not (root / "ready").exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert (root / "ready").exists(), "launcher did not reach the worker"
        # Rewrite in place to shift the file offsets of the final commands.
        # This reproduced the reported line-189 syntax error in the old GPT script.
        script.write_text(original.replace("set -", "# edit during run\n# another comment\nset -", 1))
        (root / "release").touch()
        stdout, stderr = process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            (root / "release").touch()
            process.kill()
            process.communicate(timeout=10)

    expected = 17 if name == "publish_site.sh" and worker_fails else int(worker_fails)
    assert process.returncode == expected, stdout + stderr
    assert not stderr, stderr
    if name == "publish_site.sh":
        assert ("Dry run complete" in stdout) is (not worker_fails)
    else:
        assert "=== DONE:" in stdout
        assert ("STILL FAILING (check " in stdout) is worker_fails
        assert set((root / "logs").glob("*.log")) == {root / "logs/NVDA.log"}
    assert not (root / ".tradingagents/run_missing_today_gpt.lock").exists()
