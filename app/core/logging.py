"""Structured JSON logging with a per-pipeline-run correlation id."""

import asyncio
import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

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
    root = logging.getLogger()
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(JsonFormatter())
    root.addHandler(console)

    # Optional durable log. stdout alone scrolls away with the terminal, so on an
    # unattended run a failing job leaves no traceback to read afterwards —
    # which is exactly how weeks of screener failures went unnoticed.
    path = os.environ.get("ASSISTANT_LOG_FILE", "").strip()
    if path:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            rotating = RotatingFileHandler(
                path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            rotating.setFormatter(JsonFormatter())
            root.addHandler(rotating)
        except OSError:
            # Never let logging setup stop the service from starting.
            logger.exception("Could not open ASSISTANT_LOG_FILE %r", path)

    root.setLevel(level)
    # Third-party chatter that drowns out the signal at INFO.
    for noisy in ("httpx", "httpcore", "urllib3", "apscheduler.executors"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
