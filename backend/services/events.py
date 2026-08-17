from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any


class AnalysisEventBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def publish(self, analysis_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {
            "type": event_type,
            "analysis_id": analysis_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            **(payload or {}),
        }
        self._history[analysis_id].append(event)
        for queue in list(self._queues.get(analysis_id, [])):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                continue
        return event

    def history(self, analysis_id: str) -> list[dict[str, Any]]:
        return list(self._history.get(analysis_id, []))

    async def subscribe(self, analysis_id: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._queues[analysis_id].append(queue)
        try:
            for item in self.history(analysis_id):
                yield item
            while True:
                event = await queue.get()
                yield event
        finally:
            listeners = self._queues.get(analysis_id, [])
            if queue in listeners:
                listeners.remove(queue)


event_bus = AnalysisEventBus()


def sse_pack(event: dict[str, Any]) -> str:
    return f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, default=str)}\n\n"
