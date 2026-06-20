"""Observer: enriches raw events with timing, full payloads, and correlations."""
from __future__ import annotations

import time
from datetime import datetime, timezone


class Observer:
    def __init__(self):
        self._seq = 0
        self._tool_starts: dict[str, float] = {}
        self._agent_starts: dict[str, float] = {}

    def enrich(self, event_type: str, data: dict) -> dict:
        self._seq += 1
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        enriched = {
            "observer_seq": self._seq,
            "observer_ts": now,
            "type": event_type,
            "data": dict(data),
        }

        if event_type == "tool_call":
            tool_name = data.get("tool", "unknown")
            self._tool_starts[tool_name] = time.monotonic()
        elif event_type == "tool_result":
            tool_name = data.get("tool", "unknown")
            start = self._tool_starts.pop(tool_name, None)
            if start is not None:
                enriched["data"]["duration_ms"] = int((time.monotonic() - start) * 1000)

        if event_type == "analyst_started":
            node = data.get("node", "unknown")
            self._agent_starts[node] = time.monotonic()
        elif event_type == "analyst_completed":
            node = data.get("node", "")
            start = self._agent_starts.pop(node, None)
            if start is not None:
                enriched["data"]["duration_ms"] = int((time.monotonic() - start) * 1000)

        return enriched
