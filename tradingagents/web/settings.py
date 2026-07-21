"""Persist last-used run settings as the configure form's defaults.

``backend_url`` is secret-adjacent (keyed relays embed tokens in URLs): it is
never persisted here and never echoed to the browser.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EXCLUDED_KEYS = frozenset({"backend_url"})

_DEFAULT_PATH = Path(os.path.expanduser("~")) / ".tradingagents" / "web_settings.json"


def settings_path() -> Path:
    return _DEFAULT_PATH


def load_settings(path: Path | None = None) -> dict[str, Any]:
    path = path or settings_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Unreadable web settings file: %s", path)
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k not in EXCLUDED_KEYS}


def save_settings(settings: dict[str, Any], path: Path | None = None) -> None:
    path = path or settings_path()
    cleaned = {k: v for k, v in settings.items() if k not in EXCLUDED_KEYS}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    except OSError:
        logger.warning("Could not persist web settings to %s", path)
