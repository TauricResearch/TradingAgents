"""Share analysis results through a dedicated branch of a GitHub repo.

Layout on the results branch (one tiny JSON file per run)::

    results/<deep_model>__<quick_model>/<YYYY-MM-DD>/<TICKER>.json

Lookup is a single anonymous GET to raw.githubusercontent.com (a 404 means "not
analysed yet"); publishing writes into a local clone and pushes in batches.
Disabled unless ``SHARE_RESULTS_ENABLED=true``. Every failure is logged and
swallowed so sharing never breaks an analysis run.
"""

from __future__ import annotations

import atexit
import base64
import datetime
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

_lock = threading.Lock()
_pending = 0
_last_push = time.monotonic()
_ready = False


def _env(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip()


def is_enabled() -> bool:
    return _env("SHARE_RESULTS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _repo() -> str:
    return _env("SHARE_RESULTS_REPO", "vkhera/TradingAgents")


def _branch() -> str:
    return _env("SHARE_RESULTS_BRANCH", "results-data")


def _clone_dir() -> Path:
    return Path(_env("SHARE_RESULTS_DIR", ".share_results"))


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip()).strip("-") or "unknown"


def result_path(ticker: str, analysis_date: str, deep_model: str, quick_model: str) -> str:
    combo = f"{_slug(deep_model)}__{_slug(quick_model)}"
    return f"results/{combo}/{_slug(str(analysis_date))}/{_slug(ticker).upper()}.json"


def _log(msg: str) -> None:
    print(f"[Share] {msg}")


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    # Identity and credentials are passed per command so nothing is written to .git/config.
    prefix = ["-c", "user.name=TradingAgents", "-c", "user.email=tradingagents@users.noreply.github.com"]
    token = _env("SHARE_RESULTS_TOKEN", "")
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        prefix += ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic}"]
    return subprocess.run(
        ["git", *prefix, *args], cwd=_clone_dir(), capture_output=True, text=True, check=check, timeout=120
    )


def _parse(raw: str) -> dict | None:
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) and data.get("recommendation") else None


def find_existing(ticker: str, analysis_date: str, deep_model: str, quick_model: str) -> dict | None:
    """Return the shared result for this run, or None if it has not been analysed."""
    if not is_enabled():
        _log("pre-check disabled (SHARE_RESULTS_ENABLED is not true)")
        return None
    rel = result_path(ticker, analysis_date, deep_model, quick_model)
    _log(f"pre-check: looking up {rel}")

    # Unpushed local results count too.
    local = _clone_dir() / rel
    if local.is_file():
        found = _parse(local.read_text(encoding="utf-8"))
        if found:
            _log(f"pre-check HIT (local clone): {rel}")
            return found

    url = f"https://raw.githubusercontent.com/{_repo()}/{_branch()}/{rel}"
    request = urllib.request.Request(url)
    token = _env("SHARE_RESULTS_TOKEN", "")
    if token:
        request.add_header("Authorization", f"token {token}")
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            found = _parse(resp.read().decode("utf-8"))
        _log(f"pre-check {'HIT (remote)' if found else 'MISS (invalid file)'}: {rel}")
        return found
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _log(f"pre-check MISS: {rel}; running analysis")
        else:
            _log(f"pre-check lookup failed ({exc.code}) for {rel}; running analysis")
    except Exception as exc:
        _log(f"pre-check lookup failed ({exc}) for {rel}; running analysis")
    return None


def _ensure_clone() -> None:
    global _ready, _pending
    if _ready:
        return
    clone = _clone_dir()
    url = f"https://github.com/{_repo()}.git"
    if not (clone / ".git").is_dir():
        clone.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=clone, check=True)
        subprocess.run(["git", "remote", "add", "origin", url], cwd=clone, check=True)
    fetched = _git("fetch", "origin", _branch(), check=False)
    has_local = _git("rev-parse", "--verify", "-q", "HEAD", check=False).returncode == 0
    if fetched.returncode == 0 and has_local:
        # Keep unpushed commits from a previous session and count them.
        _git("rebase", "-q", "FETCH_HEAD", check=False)
        ahead = _git("rev-list", "--count", "FETCH_HEAD..HEAD", check=False).stdout.strip()
        _pending = int(ahead) if ahead.isdigit() else 0
    elif fetched.returncode == 0:
        _git("checkout", "-q", "-B", _branch(), "FETCH_HEAD")
    else:
        # Branch does not exist remotely yet: start it as an orphan.
        _git("checkout", "-q", "--orphan", _branch(), check=False)
    _ready = True


def _push_locked() -> None:
    global _pending, _last_push
    if _pending == 0:
        return
    for _ in range(3):
        if _git("push", "origin", f"HEAD:{_branch()}", check=False).returncode == 0:
            _log(f"pushed {_pending} result(s) to {_branch()}")
            _pending = 0
            _last_push = time.monotonic()
            return
        _git("pull", "--rebase", "-q", "origin", _branch(), check=False)
    _log(f"push failed; {_pending} result(s) stay committed locally and will be retried")


def publish(
    ticker: str,
    analysis_date: str,
    provider: str,
    deep_model: str,
    quick_model: str,
    recommendation: str,
) -> None:
    """Commit a result to the local clone and push when the batch is full or due."""
    global _pending
    if not is_enabled():
        _log("post-run publish disabled (SHARE_RESULTS_ENABLED is not true)")
        return
    rel = result_path(ticker, analysis_date, deep_model, quick_model)
    payload = {
        "ticker": ticker,
        "analysis_date": str(analysis_date),
        "llm_provider": provider,
        "deep_think_llm": deep_model,
        "quick_think_llm": quick_model,
        "recommendation": recommendation,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    try:
        with _lock:
            _ensure_clone()
            target = _clone_dir() / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            _git("add", rel)
            _git("commit", "-q", "-m", f"result {ticker} {analysis_date}")
            _pending += 1
            _log(f"post-run: committed {rel} (pending push: {_pending})")
            batch = int(_env("SHARE_RESULTS_BATCH_SIZE", "20"))
            interval = int(_env("SHARE_RESULTS_PUSH_INTERVAL_SECONDS", "300"))
            if _pending >= batch or time.monotonic() - _last_push >= interval:
                _push_locked()
    except Exception as exc:
        _log(f"publish failed for {rel}: {exc}")


def flush() -> None:
    """Push any committed-but-unpushed results."""
    if not is_enabled():
        return
    try:
        with _lock:
            if _ready:
                _push_locked()
    except Exception as exc:
        _log(f"flush failed: {exc}")


atexit.register(flush)
