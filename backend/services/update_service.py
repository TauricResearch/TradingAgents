"""Self-update: check the git remote for new commits and trigger an in-place
update + service restart.

How the restart works without the API killing itself: the actual update runs in
a SEPARATE systemd oneshot unit (``$TRADINGAGENTS_UPDATE_UNIT``) so it lives in
its own cgroup and survives restarting the main service. The API only needs the
narrow privilege to *start* that one unit (granted via a sudoers drop-in by the
installer). Everything here is sync subprocess work — call it from the API layer
via ``asyncio.to_thread`` so the event loop stays free.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

# backend/services/update_service.py -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATUS_FILE = PROJECT_ROOT / ".update.json"

# Set on the main systemd unit by the installer; absence ⇒ not installer-managed.
UPDATE_UNIT = os.environ.get("TRADINGAGENTS_UPDATE_UNIT", "")
SYSTEMCTL = os.environ.get("TRADINGAGENTS_SYSTEMCTL", "systemctl")

_FETCH_TTL = 60.0          # don't hit the network more than once per minute
_last_fetch = 0.0


def _git(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), *args],
        capture_output=True, text=True, timeout=timeout,
    )


def _read_status() -> dict | None:
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_status(data: dict) -> None:
    try:
        STATUS_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def get_status(do_fetch: bool = True) -> dict:
    """Current vs. upstream commit, how many commits behind, and update state."""
    global _last_fetch

    head = _git("rev-parse", "HEAD")
    if head.returncode != 0:
        # Not a git checkout — nothing to compare against.
        return {
            "git": False, "update_supported": False, "update_available": False,
            "updating": False, "current_short": None, "behind": 0, "commits": [],
        }
    current = head.stdout.strip()

    up = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    upstream = up.stdout.strip() if up.returncode == 0 else ""

    if do_fetch and upstream and (time.time() - _last_fetch) > _FETCH_TTL:
        _git("fetch", "--quiet", timeout=60)   # ignore failures (offline etc.)
        _last_fetch = time.time()

    latest, behind, commits = current, 0, []
    if upstream:
        lt = _git("rev-parse", upstream)
        if lt.returncode == 0:
            latest = lt.stdout.strip()
        rc = _git("rev-list", "--count", f"HEAD..{upstream}")
        if rc.returncode == 0:
            behind = int(rc.stdout.strip() or "0")
        if behind:
            lg = _git("log", "--pretty=format:%h %s", f"HEAD..{upstream}", "-n", "15")
            if lg.returncode == 0:
                commits = [l for l in lg.stdout.splitlines() if l.strip()]

    status = _read_status() or {}
    return {
        "git": True,
        "update_supported": bool(UPDATE_UNIT),
        "current": current,
        "current_short": current[:9],
        "latest_short": latest[:9],
        "behind": behind,
        "update_available": behind > 0,
        "updating": status.get("state") == "running",
        "last_update": status,
        "commits": commits,
    }


def request_update() -> dict:
    """Trigger the separate updater unit (non-blocking). Raises on misconfig."""
    if not UPDATE_UNIT:
        raise RuntimeError(
            "Otomatik güncelleme bu ortamda yapılandırılmamış "
            "(deploy/install.sh ile kurulan sistemlerde çalışır)."
        )
    status = _read_status()
    if status and status.get("state") == "running":
        raise RuntimeError("Güncelleme zaten sürüyor.")

    # Optimistic state so every client's poll immediately shows "updating".
    _write_status({"state": "running", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    try:
        subprocess.run(
            ["sudo", "-n", SYSTEMCTL, "start", "--no-block", UPDATE_UNIT],
            check=True, capture_output=True, text=True, timeout=15,
        )
    except Exception as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        _write_status({"state": "failed", "error": detail})
        raise RuntimeError(f"Güncelleme başlatılamadı: {detail}")

    return {"started": True}
