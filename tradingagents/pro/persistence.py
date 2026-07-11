"""Shared durable-write helpers for the /data volume.

Two write disciplines cover every persistence need in the pro package:

- ``atomic_write_text``/``atomic_write_json``: whole-file replacement via
  temp file + fsync + ``os.replace`` — a crash mid-write leaves the old
  file intact, never a torn one.
- ``append_line_fsync``: append-only logs (audit chain, WALs) where each
  accepted line must survive power loss before the caller proceeds.

Extracted from the previously duplicated inline pattern in
``dashboard/prefs.py`` and ``dashboard/recorder.py``; the go-live OMS
journal builds on the same primitives.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

__all__ = ["atomic_write_text", "atomic_write_json", "append_line_fsync"]


def atomic_write_text(path: str | Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, suffix=".tmp", delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
    os.replace(tmp.name, path)


def atomic_write_json(path: str | Path, obj, *, indent: int | None = None) -> None:
    atomic_write_text(path, json.dumps(obj, sort_keys=True, indent=indent))


def append_line_fsync(path: str | Path, line: str) -> None:
    """Append one line and fsync before returning — the caller may treat
    the record as committed (write-ahead discipline)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line.rstrip("\n") + "\n")
        handle.flush()
        os.fsync(handle.fileno())
