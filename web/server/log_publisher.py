"""Log publisher: custom logging.Handler that broadcasts records over WebSocket."""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Set

from fastapi import WebSocket


class LogPublisher(logging.Handler):
    """Custom logging.Handler that broadcasts records to WebSocket subscribers."""

    def __init__(self, min_level: int = logging.INFO) -> None:
        super().__init__(level=min_level)
        self._subscribers: Set[WebSocket] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def min_level(self) -> int:
        return self.level

    @min_level.setter
    def min_level(self, value: int) -> None:
        self.setLevel(value)

    def subscribe(self, ws: WebSocket) -> None:
        with self._lock:
            self._subscribers.add(ws)

    def unsubscribe(self, ws: WebSocket) -> None:
        with self._lock:
            self._subscribers.discard(ws)

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < self.level:
            return
        entry = {
            "id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": self.format(record),
            "source": "server",
        }
        targets: list[WebSocket] = []
        with self._lock:
            targets.extend(self._subscribers)
        for ws in targets:
            try:
                if self._loop and not self._loop.is_closed():
                    asyncio.run_coroutine_threadsafe(ws.send_json(entry), self._loop)
                else:
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(ws.send_json(entry))
                    finally:
                        loop.close()
            except Exception:
                pass

    def handle(self, record: logging.LogRecord) -> bool:
        self.emit(record)
        return True


_log_publisher: LogPublisher | None = None


def setup_log_publisher(loop: asyncio.AbstractEventLoop, min_level: int = logging.INFO) -> LogPublisher:
    global _log_publisher
    _log_publisher = LogPublisher(min_level=min_level)
    _log_publisher._loop = loop
    root = logging.getLogger()
    root.addHandler(_log_publisher)
    return _log_publisher


def teardown_log_publisher() -> None:
    global _log_publisher
    if _log_publisher is not None:
        root = logging.getLogger()
        root.removeHandler(_log_publisher)
        _log_publisher = None


def get_log_publisher() -> LogPublisher | None:
    return _log_publisher


# Module-level singleton accessor for use in app.py
def log_publisher() -> LogPublisher | None:
    return _log_publisher