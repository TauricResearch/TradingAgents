"""Cloud persistence for watchlist data via Render environment variables.

On Render, the filesystem is ephemeral — data written to disk is lost on
redeploy.  This module bridges the gap by keeping a backup of the watchlist
in a Render environment variable (which persists across deploys).

Usage
-----
On app startup, call ``restore_watchlist()`` after ``storage.init_settings()``.
After every write to the watchlist JSON file, call ``backup_watchlist()``.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

BACKUP_ENV_VAR = "TRADINGAGENTS_WATCHLIST_BACKUP"
WATCHLIST_FILE = "watchlist.json"


def _api_key() -> str | None:
    return os.environ.get("RENDER_API_KEY")


def _service_id() -> str | None:
    return os.environ.get("RENDER_SERVICE_ID")


def restore_watchlist(data_dir: str | Path) -> None:
    """Restore the watchlist from the backup env var (if no local file exists)."""
    watchlist_path = Path(data_dir) / WATCHLIST_FILE
    if watchlist_path.exists():
        return

    raw = os.environ.get(BACKUP_ENV_VAR) or ""
    if not raw:
        return

    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        data = json.loads(decoded)
        watchlist_path.parent.mkdir(parents=True, exist_ok=True)
        watchlist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        log.info("restored watchlist from env var (%d tickers)", len(data.get("tickers", [])))
    except Exception:
        log.exception("failed to restore watchlist from env var")


def backup_watchlist(data_dir: str | Path) -> None:
    """Backup the current watchlist to the Render env var."""
    watchlist_path = Path(data_dir) / WATCHLIST_FILE
    if not watchlist_path.exists():
        return

    key = _api_key()
    sid = _service_id()
    if not key or not sid:
        return

    try:
        raw = watchlist_path.read_text(encoding="utf-8")
        encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        body = json.dumps([{"key": BACKUP_ENV_VAR, "value": encoded}]).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.render.com/v1/services/{sid}/env-vars",
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="PUT",
        )
        urllib.request.urlopen(req, timeout=10)
        log.debug("watchlist backed up to env var")
    except Exception:
        log.exception("failed to backup watchlist to env var")
