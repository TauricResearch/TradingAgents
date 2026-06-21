"""Observer: enriches raw events with timing, full payloads, and correlations."""
from __future__ import annotations

import time
from datetime import datetime, timezone


class Observer:
    def __init__(self):
        self._seq = 0
        self._tool_starts: dict[str, float] = {}
        self._agent_starts: dict[str, float] = {}
        self._ticker_step_starts: dict[int, float] = {}
        self._ticker_cycle_start: float | None = None

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

    def ticker_enrich(self, event: dict) -> dict:
        self._seq += 1
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        event_type = event.get("event_type", "")

        enriched = {
            "observer_seq": self._seq,
            "observer_ts": now,
            "id": event.get("id"),
            "step": event.get("step", 0),
            "step_name": event.get("step_name", ""),
            "message": event.get("message", ""),
            "timestamp": event.get("timestamp", now),
            "event_type": event_type,
            "detail": dict(event.get("detail", {})),
        }

        if event_type == "ticker_cycle_started":
            self._ticker_cycle_start = time.monotonic()
            enriched["detail"]["cycle_number"] = event.get("detail", {}).get("cycle_number")

        elif event_type == "ticker_step_started":
            step = event.get("step", 0)
            self._ticker_step_starts[step] = time.monotonic()

        elif event_type == "ticker_step_completed":
            step = event.get("step", 0)
            start = self._ticker_step_starts.pop(step, None)
            if start is not None:
                enriched["detail"]["duration_ms"] = int((time.monotonic() - start) * 1000)

        elif event_type == "ticker_llm_call":
            start = self._ticker_step_starts.get(3)
            if start is not None:
                enriched["detail"]["duration_ms"] = int((time.monotonic() - start) * 1000)

        elif event_type == "ticker_data_fetch":
            pass

        elif event_type == "ticker_cycle_completed":
            if self._ticker_cycle_start is not None:
                enriched["detail"]["total_duration_ms"] = int((time.monotonic() - self._ticker_cycle_start) * 1000)
                self._ticker_cycle_start = None

        return enriched
