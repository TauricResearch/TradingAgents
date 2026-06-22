"""Event envelope + SSE framing. Dependency-free (no FastAPI / tradingagents),
so it is unit-testable on any interpreter and shares the schema version with
``desk_adapter.protocol``.
"""

from __future__ import annotations

import json
import time
from typing import Any

from desk_adapter.protocol import SCHEMA_VERSION


def build_event(run_id: str, seq: int, event_type: str, fields: dict[str, Any],
                clock=time.time) -> dict:
    """Wrap an event in the shared envelope (mirrors desk_adapter.protocol.Emitter)."""
    obj = {
        "v": SCHEMA_VERSION,
        "run_id": run_id,
        "seq": seq,
        "ts": round(clock(), 3),
        "type": event_type,
    }
    obj.update(fields)
    return obj


def sse_format(event: dict) -> str:
    """Render one event as an SSE frame. ``id:`` carries ``seq`` so a reconnecting
    client can resume via the ``Last-Event-ID`` header."""
    payload = json.dumps(event, separators=(",", ":"), ensure_ascii=False, default=str)
    return f"id: {event['seq']}\ndata: {payload}\n\n"
