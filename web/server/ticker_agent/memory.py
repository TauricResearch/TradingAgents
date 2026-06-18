"""Agent memory — persistent conclusions log for the ticker accuracy agent.

Each cycle, the agent appends structured conclusions. On the next cycle,
the last N entries are loaded and fed into the LLM prompt for context.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def _default_path() -> str:
    from web.server import storage

    return str(storage.ticker_agent_path("agent_memory.jsonl"))


def append_memory(entry: dict, file_path: str | None = None) -> None:
    """Append a memory entry to the JSONL file."""
    path = Path(file_path or _default_path())
    entry.setdefault(
        "timestamp",
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        log.warning("Failed to append memory: %s", e)


def read_memory(limit: int = 10, file_path: str | None = None) -> list[dict]:
    """Read the most recent N memory entries, newest first."""
    path = Path(file_path or _default_path())
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        entries: list[dict] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        entries.reverse()
        return entries[:limit]
    except OSError as e:
        log.warning("Failed to read memory: %s", e)
        return []
