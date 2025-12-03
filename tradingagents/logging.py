import logging
import logging.handlers
import os
import json
from datetime import datetime

LOG_LEVEL_DEFAULT = "INFO"
LOG_DIR_DEFAULT = "./logs"
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


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return bool(value)


def _get_config_value(key, default):
    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        return DEFAULT_CONFIG.get(key, default)
    except ImportError:
        return default


def setup_logging():
    global _logging_initialized

    log_level_str = os.getenv("TRADINGAGENTS_LOG_LEVEL")
    if log_level_str is None:
        log_level_str = _get_config_value("log_level", LOG_LEVEL_DEFAULT)

    log_dir = os.getenv("TRADINGAGENTS_LOG_DIR")
    if log_dir is None:
        log_dir = _get_config_value("log_dir", LOG_DIR_DEFAULT)

    console_enabled_env = os.getenv("TRADINGAGENTS_LOG_CONSOLE")
    if console_enabled_env is not None:
        console_enabled = _parse_bool(console_enabled_env)
    else:
        console_enabled = _get_config_value("log_console_enabled", True)

    file_enabled_env = os.getenv("TRADINGAGENTS_LOG_FILE")
    if file_enabled_env is not None:
        file_enabled = _parse_bool(file_enabled_env)
    else:
        file_enabled = _get_config_value("log_file_enabled", True)

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
        from rich.logging import RichHandler
        from rich.console import Console

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
