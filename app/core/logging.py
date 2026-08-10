"""Structured JSON logging with a per-pipeline-run correlation id."""

import asyncio
import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def log_task_exception(task: asyncio.Task) -> None:
    """done-callback that surfaces a fire-and-forget task's failure.

    ``add_done_callback(set.discard)`` alone never retrieves the exception, so a
    crashed background task is invisible until an eventual "Task exception was
    never retrieved" at GC time — which is how weeks of screener failures left
    no trace.
    """
    if task.cancelled():
        logger.error("Background task %s cancelled", task.get_name())
        return
    error = task.exception()
    if error is not None:
        logger.error("Background task %s failed", task.get_name(), exc_info=error)

# Set by the pipeline at the start of each market run; every log line emitted
# during that run (including from tradingagents internals) carries the id.
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        run_id = run_id_var.get()
        if run_id:
            payload["run_id"] = run_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # Third-party chatter that drowns out the signal at INFO.
    for noisy in ("httpx", "httpcore", "urllib3", "apscheduler.executors"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
