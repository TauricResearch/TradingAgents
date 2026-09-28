"""JSONL audit log for the execution bridge.

One JSON object per line, append-only, UTF-8 (the Windows default is cp1252
and this project fixed UTF-8 bugs before). The writer is deliberately dumb:
the caller builds the event dict, this module only persists it. No API key or
secret ever passes through here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_event(path: str | Path, event: dict[str, Any]) -> None:
    """Append ``event`` as one JSON line to ``path``, creating parents as needed."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
