import json
import logging
import logging.handlers
import os
from datetime import datetime

LOG_FILE_NAME = "tradingagents.log"
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5

_logging_initialized = False


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "filename": record.filename,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


def _get_settings():
    try:
        from tradingagents.config import get_settings

        return get_settings()
    except ImportError:
        return None


def setup_logging():
    global _logging_initialized

    settings = _get_settings()

    if settings:
        log_level_str = settings.log_level
        log_dir = settings.log_dir
        console_enabled = settings.log_console_enabled
        file_enabled = settings.log_file_enabled
    else:
        log_level_str = os.getenv("TRADINGAGENTS_LOG_LEVEL", "INFO")
        log_dir = os.getenv("TRADINGAGENTS_LOG_DIR", "./logs")
        console_enabled = os.getenv("TRADINGAGENTS_LOG_CONSOLE", "true").lower() in (
            "true",
            "1",
            "yes",
            "on",
        )
        file_enabled = os.getenv("TRADINGAGENTS_LOG_FILE", "true").lower() in (
            "true",
            "1",
            "yes",
            "on",
        )

    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    root_logger = logging.getLogger("tradingagents")

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.setLevel(log_level)

    if file_enabled:
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, LOG_FILE_NAME)

        file_handler = logging.handlers.RotatingFileHandler(
            log_file_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

    if console_enabled:
        from rich.console import Console
        from rich.logging import RichHandler

        console = Console(stderr=True)
        rich_handler = RichHandler(
            console=console,
            show_time=True,
            show_level=True,
            show_path=True,
            rich_tracebacks=True,
        )
        rich_handler.setLevel(log_level)
        root_logger.addHandler(rich_handler)

    _logging_initialized = True

    return root_logger


def get_logger(name):
    global _logging_initialized

    if not _logging_initialized:
        setup_logging()

    return logging.getLogger(name)
