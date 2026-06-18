"""Missing capabilities tracking for the ticker accuracy agent.

Logs capabilities the agent identifies as missing so the user
can review and request implementation.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class MissingCapability:
    name: str
    description: str
    suggested_endpoint: str | None = None
    logged_at: str | None = None


def _default_path() -> str:
    from web.server import storage

    return str(storage.ticker_agent_path("missing_capabilities.jsonl"))


def log_missing(
    name: str,
    description: str,
    suggested_endpoint: str | None = None,
    file_path: str | None = None,
) -> None:
    """Log a missing capability to the append-only JSONL file."""
    path = Path(file_path or _default_path())
    entry = {
        "name": name,
        "description": description,
        "suggested_endpoint": suggested_endpoint,
        "logged_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        log.warning("Failed to log missing capability %s: %s", name, e)


def read_missing(file_path: str | None = None) -> list[MissingCapability]:
    """Read all logged missing capabilities, most recent first."""
    path = Path(file_path or _default_path())
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        entries: list[MissingCapability] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                entries.append(MissingCapability(
                    name=data.get("name", "unknown"),
                    description=data.get("description", ""),
                    suggested_endpoint=data.get("suggested_endpoint"),
                    logged_at=data.get("logged_at"),
                ))
            except json.JSONDecodeError:
                continue
        entries.reverse()
        return entries
    except OSError as e:
        log.warning("Failed to read missing capabilities: %s", e)
        return []
