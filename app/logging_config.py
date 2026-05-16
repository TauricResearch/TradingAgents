"""
Logging setup. JSON output in production for log-aggregator-friendly
output (Railway pipes stdout/stderr to its log search); human-readable
in development.

Sentry's logging integration auto-installs as a breadcrumb collector,
so anything we log at INFO+ shows up in the breadcrumb trail on captured
events. No extra wiring needed beyond `init_sentry()` in observability.py.

Treat as a python-temp-pro template — drop into any service unchanged.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.config import settings


class JSONFormatter(logging.Formatter):
    """Single-line JSON per log record. Suitable for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts":      datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level":   record.levelname,
            "logger":  record.name,
            "message": record.getMessage(),
        }
        # Surface exception info when present.
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Pull through any extras (logger.info("...", extra={"key": ...})).
        skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
        }
        for key, value in record.__dict__.items():
            if key in skip:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """
    Install handlers + formatters. Call once at startup, before any
    application code logs anything. Idempotent — clears existing
    handlers so it's safe to call again under uvicorn --reload.
    """
    is_prod = settings.NODE_ENV == "production"
    level = logging.INFO if is_prod else logging.DEBUG

    handler = logging.StreamHandler(sys.stdout)
    if is_prod:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet down some chatty loggers in production. Tune as ops needs grow.
    logging.getLogger("uvicorn.access").setLevel(logging.INFO if is_prod else logging.DEBUG)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
