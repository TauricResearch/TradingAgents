"""Async database log handler — pipes Python logging into the system_logs table.

Usage (main.py lifespan):
    await db_log_handler.start()   # on startup
    db_log_handler.stop()          # on shutdown

Once started, every _logger.info / warning / error call made anywhere in
the backend is automatically captured and written to system_logs in
background batches.
"""
import asyncio
import logging
from datetime import datetime, timezone

_BATCH_SIZE = 30          # flush when batch reaches this size
_FLUSH_INTERVAL = 3.0     # also flush every N seconds even if batch is small
_QUEUE_MAXSIZE = 2000     # drop oldest if queue is full (never block the app)

# Only these sources are captured at INFO level; everything else needs WARNING+
_VERBOSE_PREFIXES = (
    "backend.services.",
    "backend.api.",
    "backend.core.websocket",
)


class _BackendFilter(logging.Filter):
    """Include INFO+ for backend services; WARNING+ for everything else."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True  # always keep warnings and errors
        if record.levelno == logging.INFO:
            return any(record.name.startswith(p) for p in _VERBOSE_PREFIXES)
        return False  # drop DEBUG


class DatabaseLogHandler(logging.Handler):
    """Non-blocking logging handler that batches records into system_logs."""

    def __init__(self):
        super().__init__()
        self.addFilter(_BackendFilter())
        self._queue: asyncio.Queue | None = None
        self._task: asyncio.Task | None = None
        self._started = False

    async def start(self):
        """Call once from the FastAPI lifespan (async context)."""
        if self._started:
            return
        self._queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._task = asyncio.create_task(self._worker(), name="db-log-worker")
        self._started = True

    def stop(self):
        """Signal the worker to drain and exit."""
        if self._queue is not None:
            try:
                self._queue.put_nowait(None)   # sentinel
            except asyncio.QueueFull:
                pass

    def emit(self, record: logging.LogRecord):
        """Called synchronously by logging framework — must not block."""
        if not self._started or self._queue is None:
            return
        try:
            self._queue.put_nowait({
                "level":   record.levelname,
                "source":  record.name,
                "message": self.format(record),
                "details": self._exc_text(record),
            })
        except asyncio.QueueFull:
            pass  # silently drop — logging must never stall the event loop

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _exc_text(record: logging.LogRecord) -> str | None:
        if record.exc_info:
            import traceback
            return "".join(traceback.format_exception(*record.exc_info))
        return None

    async def _worker(self):
        """Drain the queue in batches; flush on timeout or batch-full."""
        from backend.core.database import AsyncSessionLocal
        from backend.models.log import SystemLog

        batch: list[dict] = []

        async def flush():
            if not batch:
                return
            items = batch.copy()
            batch.clear()
            try:
                async with AsyncSessionLocal() as db:
                    for entry in items:
                        db.add(SystemLog(
                            level=entry["level"],
                            source=entry["source"],
                            message=entry["message"],
                            details=entry["details"],
                        ))
                    await db.commit()
            except Exception:
                pass  # never crash the worker over a logging error

        while True:
            try:
                entry = await asyncio.wait_for(
                    self._queue.get(),  # type: ignore[union-attr]
                    timeout=_FLUSH_INTERVAL,
                )
                if entry is None:      # sentinel → drain and exit
                    await flush()
                    return
                batch.append(entry)
                if len(batch) >= _BATCH_SIZE:
                    await flush()
            except asyncio.TimeoutError:
                await flush()


# ── Singleton ────────────────────────────────────────────────────────────────
db_log_handler = DatabaseLogHandler()

# Attach to the root logger with a plain formatter (no timestamp — DB has created_at)
_fmt = logging.Formatter("%(message)s")
db_log_handler.setFormatter(_fmt)

# Register on the root logger so it catches everything that passes the filter
logging.getLogger().addHandler(db_log_handler)
