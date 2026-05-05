"""Rolling decision memory log."""

from __future__ import annotations

import re

from fastapi import APIRouter

from gui.log_browser import memory_log_path, read_memory_log
from service.schemas import MemoryEntry, MemoryResponse

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=MemoryResponse)
def get_memory() -> MemoryResponse:
    raw = read_memory_log()
    chunks = [c for c in re.split(r"^##\s+", raw, flags=re.MULTILINE) if c.strip()]
    entries: list[MemoryEntry] = []
    for c in chunks[1:] if chunks and not chunks[0].startswith("TICKER") else chunks:
        # Skip the header chunk if present.
        body = "## " + c
        entries.append(MemoryEntry(raw=body, resolved="REFLECTION:" in body))

    resolved = sum(1 for e in entries if e.resolved)
    return MemoryResponse(
        path=str(memory_log_path()),
        entries=entries,
        total=len(entries),
        resolved_count=resolved,
        pending_count=len(entries) - resolved,
    )
