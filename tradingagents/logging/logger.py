"""
Structured logging system for TradingAgents.

Provides severity-based logging (debug/info/warning/error) with context
enrichment (ticker, date, agent, run_id) and persistent storage under
``logs/`` in JSON Lines format.

Integration with Python's stdlib ``logging`` module ensures existing
``logger.warning()`` calls across the codebase are captured.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = ["StructuredLogger", "get_logger", "LogContext"]

_log_level = ContextVar("_log_level", default="INFO")
_ticker = ContextVar("_ticker", default=None)
_analysis_date = ContextVar("_analysis_date", default=None)
_agent = ContextVar("_agent", default=None)
_run_id = ContextVar("_run_id", default=None)


class LogContext:
    """Thread-safe, contextvar-based log context.

    Use as a context manager to scope context to a block::

        with LogContext(ticker="SPY", date="2026-05-10", agent="Market Analyst"):
            logger.info("Fetching price data")

    Or manually set/reset::

        LogContext.set_ticker("SPY")
        ...
        LogContext.reset_ticker()
    """

    @staticmethod
    def set_run_id(run_id: str) -> None:
        _run_id.set(run_id)

    @staticmethod
    def get_run_id() -> Optional[str]:
        return _run_id.get()

    @staticmethod
    def set_ticker(ticker: str) -> None:
        _ticker.set(ticker)

    @staticmethod
    def get_ticker() -> Optional[str]:
        return _ticker.get()

    @staticmethod
    def set_date(date: str) -> None:
        _analysis_date.set(date)

    @staticmethod
    def get_date() -> Optional[str]:
        return _analysis_date.get()

    @staticmethod
    def set_agent(agent: str) -> None:
        _agent.set(agent)

    @staticmethod
    def get_agent() -> Optional[str]:
        return _agent.get()

    @staticmethod
    def set_level(level: str) -> None:
        _log_level.set(level.upper())

    @staticmethod
    def get_level() -> str:
        return _log_level.get()

    @staticmethod
    def reset() -> None:
        """Reset all context to defaults."""
        _log_level.set("INFO")
        _ticker.set(None)
        _analysis_date.set(None)
        _agent.set(None)

    @staticmethod
    def snapshot() -> Dict[str, Any]:
        """Return current context as a dict."""
        ctx = {
            "level": _log_level.get(),
            "run_id": _run_id.get(),
            "ticker": _ticker.get(),
            "date": _analysis_date.get(),
            "agent": _agent.get(),
        }
        return {k: v for k, v in ctx.items() if v is not None}

    def __init__(self, **context):
        self._context = context
        self._saved: Dict[str, Any] = {}

    def __enter__(self):
        field_map = {
            "ticker": (_ticker, "get_ticker"),
            "date": (_analysis_date, "get_date"),
            "agent": (_agent, "get_agent"),
            "level": (_log_level, "get_level"),
            "run_id": (_run_id, "get_run_id"),
        }
        for key, value in self._context.items():
            if key in field_map:
                cv, _ = field_map[key]
                self._saved[key] = cv.get()
                cv.set(value)
        return self

    def __exit__(self, *args):
        field_map = {
            "ticker": _ticker,
            "date": _analysis_date,
            "agent": _agent,
            "level": _log_level,
            "run_id": _run_id,
        }
        for key, saved_value in self._saved.items():
            if key in field_map:
                field_map[key].set(saved_value)


class StructuredLogHandler(logging.Handler):
    """stdlib logging Handler that writes structured JSON Lines to ``logs/``.

    Captures all existing ``logger.warning()`` etc. calls and enriches them
    with the current LogContext.
    """

    def __init__(self, log_dir: Path, run_id: str):
        super().__init__()
        self._log_dir = log_dir
        self._run_id = run_id
        self._lock = threading.Lock()
        self._file = None
        self._current_path: Optional[Path] = None

    def _ensure_file(self) -> Path:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        path = self._log_dir / f"{self._run_id}.jsonl"
        if path != self._current_path:
            if self._file:
                self._file.close()
            self._file = open(path, "a", encoding="utf-8")
            self._current_path = path
        return path

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "timestamp": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).isoformat(),
                "level": record.levelname,
                "module": record.name,
                "message": record.getMessage(),
                "run_id": _run_id.get(),
                "ticker": _ticker.get(),
                "date": _analysis_date.get(),
                "agent": _agent.get(),
                "func": record.funcName,
                "line": record.lineno,
            }
            if record.exc_info and record.exc_info[1]:
                entry["exception"] = str(record.exc_info[1])

            with self._lock:
                self._ensure_file()
                self._file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                self._file.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        with self._lock:
            if self._file:
                self._file.close()
                self._file = None
        super().close()


class StructuredLogger:
    """Primary logger for TradingAgents with severity levels and context enrichment.

    Usage::

        logger = StructuredLogger("tradingagents")
        logger.info("Starting analysis", ticker="SPY", date="2026-05-10")
        logger.error("API call failed", exception=str(e), endpoint="...")

    Logs are written to ``logs/<ticker>/<date>/<run_id>.jsonl``.
    """

    def __init__(self, name: str, log_dir: Optional[Path] = None, run_id: Optional[str] = None):
        self._name = name
        self._log_dir = Path(log_dir) if log_dir else Path("logs")
        self._run_id = run_id or uuid.uuid4().hex[:12]
        self._stdlib_logger = logging.getLogger(name)
        self._stdlib_logger.setLevel(logging.DEBUG)

        self._handler = StructuredLogHandler(self._log_dir, self._run_id)
        self._handler.setLevel(logging.DEBUG)
        self._stdlib_logger.addHandler(self._handler)

        LogContext.set_run_id(self._run_id)

    @property
    def run_id(self) -> str:
        return self._run_id

    def _emit(self, level: int, message: str, **context) -> None:
        saved_ticker = _ticker.get()
        saved_date = _analysis_date.get()
        saved_agent = _agent.get()

        if "ticker" in context:
            _ticker.set(context.pop("ticker"))
        if "date" in context:
            _analysis_date.set(context.pop("date"))
        if "agent" in context:
            _agent.set(context.pop("agent"))

        try:
            extra = {}
            if context:
                escaped = {}
                for k, v in context.items():
                    try:
                        escaped[k] = str(v)
                    except Exception:
                        escaped[k] = "<unserializable>"
                extra["context"] = escaped
            self._stdlib_logger.log(level, message, extra=extra)
        finally:
            _ticker.set(saved_ticker)
            _analysis_date.set(saved_date)
            _agent.set(saved_agent)

    def debug(self, message: str, **context) -> None:
        self._emit(logging.DEBUG, message, **context)

    def info(self, message: str, **context) -> None:
        self._emit(logging.INFO, message, **context)

    def warning(self, message: str, **context) -> None:
        self._emit(logging.WARNING, message, **context)

    def error(self, message: str, **context) -> None:
        self._emit(logging.ERROR, message, **context)

    def close(self) -> None:
        self._handler.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


_loggers: Dict[str, StructuredLogger] = {}
_lock = threading.Lock()


def get_logger(
    name: str = "tradingagents",
    log_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> StructuredLogger:
    """Get or create a StructuredLogger instance.

    Cached by name so the same instance is returned across the application.
    """
    with _lock:
        if name not in _loggers:
            _loggers[name] = StructuredLogger(name, log_dir=log_dir, run_id=run_id)
        return _loggers[name]
