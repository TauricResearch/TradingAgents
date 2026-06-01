import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

_logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages per-task WebSocket connections for streaming analysis progress."""

    def __init__(self):
        # task_id → list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, task_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(task_id, []).append(ws)
        _logger.debug("WS connected: task=%s total=%d", task_id, len(self._connections[task_id]))

    def disconnect(self, task_id: str, ws: WebSocket):
        conns = self._connections.get(task_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(task_id, None)

    async def send(self, task_id: str, event: dict[str, Any]):
        """Broadcast a JSON event to all connections listening on task_id."""
        text = json.dumps(event, ensure_ascii=False)
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(task_id, [])):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(task_id, ws)

    async def close_task(self, task_id: str):
        """Close all connections for a finished task."""
        for ws in list(self._connections.get(task_id, [])):
            try:
                await ws.close()
            except Exception:
                pass
        self._connections.pop(task_id, None)

    def active_tasks(self) -> list[str]:
        return list(self._connections.keys())


# Singleton instance shared across the app
ws_manager = WebSocketManager()
