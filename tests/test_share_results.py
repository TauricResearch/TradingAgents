import subprocess

from api import share


def test_result_path_sanitizes_models():
    p = share.result_path("aapl", "2026-10-12", "qwen3:latest", "org/model:free")
    assert p == "results/qwen3-latest__org-model-free/2026-10-12/AAPL.json"


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SHARE_RESULTS_ENABLED", raising=False)
    assert share.find_existing("AAPL", "2026-10-12", "a", "b") is None


def test_publish_then_find_locally(monkeypatch, tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    monkeypatch.setenv("SHARE_RESULTS_ENABLED", "true")
    monkeypatch.setenv("SHARE_RESULTS_DIR", str(tmp_path / "clone"))
    monkeypatch.setenv("SHARE_RESULTS_BATCH_SIZE", "1")
    monkeypatch.setattr(share, "_ready", False)
    monkeypatch.setattr(share, "_pending", 0)
    monkeypatch.setattr(share, "_repo", lambda: "unused")

    real_git = share._git

    def git(*args, check=True):
        if args[:3] == ("fetch", "origin", "results-data"):
            return real_git("fetch", str(bare), "results-data", check=False)
        return real_git(*args, check=check)

    monkeypatch.setattr(share, "_git", git)
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: _run(cmd, bare, **kw),
    )
    share.publish("AAPL", "2026-10-12", "ollama", "d", "q", "Buy")
    found = share.find_existing("AAPL", "2026-10-12", "d", "q")
    assert found and found["recommendation"] == "Buy"


_orig_run = subprocess.run


def _run(cmd, bare, **kw):
    if cmd[:3] == ["git", "remote", "add"]:
        cmd = [*cmd[:4], str(bare)]
    elif cmd[:2] == ["git", "push"]:
        cmd = ["git", "push", str(bare), cmd[3]]
    return _orig_run(cmd, **kw)
