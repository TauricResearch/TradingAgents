"""Tiny disk cache for data-layer fetches.

Keeps repeated tool calls within an analyst run cheap and rate-limit-safe.
TTLs default to a few minutes — enough to dedupe within a single agent
pipeline run but short enough that a re-run picks up fresh state.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional


def _cache_root() -> Path:
    from tradingagents.dataflows.config import get_config
    root = Path(get_config().get("data_cache_dir", os.path.expanduser("~/.tradingagents/cache")))
    root.mkdir(parents=True, exist_ok=True)
    return root


def cached_json(key: str, ttl_seconds: int, fetcher: Callable[[], Any]) -> Any:
    """Return ``fetcher()`` cached on disk under ``key`` for ``ttl_seconds``.

    Cache values must be JSON-serializable. ``key`` is used as a filename
    (path-safe characters only — caller is responsible for sanitization).
    """
    path = _cache_root() / f"{key}.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - payload.get("_cached_at", 0) < ttl_seconds:
                return payload["value"]
        except (json.JSONDecodeError, KeyError):
            pass

    value = fetcher()
    try:
        path.write_text(
            json.dumps({"_cached_at": time.time(), "value": value}, default=str),
            encoding="utf-8",
        )
    except (TypeError, OSError):
        # Cache writes are best-effort — never let them fail the call.
        pass
    return value
