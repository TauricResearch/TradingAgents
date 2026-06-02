import asyncio
import json
import logging
from collections import deque
from typing import Any

from fastapi import WebSocket

_logger = logging.getLogger(__name__)

# How many events to buffer per task while no client is connected yet.
# This covers the race-condition window between background task start
# and the client's first WS connect (typically < 5 seconds).
_BUFFER_SIZE = 64
# How long (seconds) to keep the buffer after the task finishes.
_BUFFER_TTL = 30


class WebSocketManager:
    """Manages per-task WebSocket connections for streaming analysis progress.

    Buffering guarantees:
    - Events sent before the client connects are queued and replayed
      when the client does connect.
    - If the task finishes before any client ever connects, the buffer
      is kept for _BUFFER_TTL seconds so a late-connecting client still
      receives the full event history (including the error/complete event).
    """

    def __init__(self):
        # task_id → list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}
        # task_id → deque of buffered events (sent before client connected)
        self._buffers: dict[str, deque] = {}
        # task_id → asyncio.TimerHandle for buffer cleanup after TTL
        self._cleanup_handles: dict[str, asyncio.TimerHandle] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    async def connect(self, task_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(task_id, []).append(ws)
        _logger.debug("WS connected: task=%s", task_id)

        # Replay any buffered events that arrived before this connection
        buffered = list(self._buffers.get(task_id, []))
        if buffered:
            _logger.debug("Replaying %d buffered events for task=%s", len(buffered), task_id)
            for event in buffered:
                try:
                    await ws.send_text(json.dumps(event, ensure_ascii=False))
                except Exception:
                    break

    def disconnect(self, task_id: str, ws: WebSocket):
        conns = self._connections.get(task_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(task_id, None)

    async def send(self, task_id: str, event: dict[str, Any]):
        """Broadcast a JSON event to all connections on task_id.

        If no client is connected yet the event is buffered so it can
        be replayed when the client eventually connects.
        """
        # Always buffer (so late-connecting clients get full history)
        buf = self._buffers.setdefault(task_id, deque(maxlen=_BUFFER_SIZE))
        buf.append(event)

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
        """Close all connections for a finished task and schedule buffer cleanup."""
        for ws in list(self._connections.get(task_id, [])):
            try:
                await ws.close()
            except Exception:
                pass
        self._connections.pop(task_id, None)

        # Keep the buffer alive for TTL so a late client can still read events
        self._schedule_buffer_cleanup(task_id)

    def active_tasks(self) -> list[str]:
        return list(self._connections.keys())

    # ── Internal ──────────────────────────────────────────────────────────────

    def _schedule_buffer_cleanup(self, task_id: str):
        """Schedule buffer removal after _BUFFER_TTL seconds."""
        # Cancel any existing handle
        existing = self._cleanup_handles.pop(task_id, None)
        if existing:
            try:
                existing.cancel()
            except Exception:
                pass

        loop = asyncio.get_event_loop()
        handle = loop.call_later(_BUFFER_TTL, self._cleanup_buffer, task_id)
        self._cleanup_handles[task_id] = handle

    def _cleanup_buffer(self, task_id: str):
        self._buffers.pop(task_id, None)
        self._cleanup_handles.pop(task_id, None)
        _logger.debug("Buffer cleaned up for task=%s", task_id)


# Singleton instance shared across the app
ws_manager = WebSocketManager()
