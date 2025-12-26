"""
Dual-Output Logging Configuration.

This module provides logging configuration that outputs to both:
1. Terminal (console) with Rich formatting
2. Rotating log files (5MB rotation, 3 backups)

Features:
- Terminal logging at INFO level by default
- File logging at DEBUG level by default
- Automatic log rotation at 5MB
- API key sanitization in log messages
- Log file creation in TRADINGAGENTS_RESULTS_DIR or ./logs

Usage:
    from spektiv.utils.logging_config import setup_dual_logger

    logger = setup_dual_logger(
        name="spektiv",
        log_file="./logs/spektiv.log"
    )

    logger.info("This goes to both terminal and file")
    logger.debug("This only goes to file")

    # API keys are automatically sanitized
    logger.error("Error with key sk-1234567890")  # Logged as [REDACTED-API-KEY]
"""

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

try:
    from rich.logging import RichHandler
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


# API key patterns to sanitize
API_KEY_PATTERNS = [
    (re.compile(r'sk-[a-zA-Z0-9\-_]+'), '[REDACTED-API-KEY]'),  # OpenAI keys
    (re.compile(r'sk-or-v\d+-[a-zA-Z0-9\-_]+'), '[REDACTED-API-KEY]'),  # OpenRouter keys
    (re.compile(r'sk-ant-[a-zA-Z0-9\-_]+'), '[REDACTED-API-KEY]'),  # Anthropic keys
    (re.compile(r'sk-proj-[a-zA-Z0-9\-_]+'), '[REDACTED-API-KEY]'),  # OpenAI project keys
    (re.compile(r'Bearer\s+[A-Za-z0-9+/\-_.=]+'), 'Bearer [REDACTED-TOKEN]'),  # Bearer tokens (incl. Base64)
]


class SanitizingFilter(logging.Filter):
    """
    Logging filter that sanitizes API keys and sensitive data from log messages.
    """

    def filter(self, record):
        """
        Sanitize the log record message.

        Args:
            record: LogRecord to sanitize

        Returns:
            bool: Always True (we modify in place, don't filter out)
        """
        if record.msg:
            record.msg = sanitize_log_message(str(record.msg))

        # Also sanitize args if present
        if record.args:
            try:
                sanitized_args = tuple(
                    sanitize_log_message(str(arg)) if isinstance(arg, str) else arg
                    for arg in record.args
                )
                record.args = sanitized_args
            except (TypeError, ValueError):
                # If args aren't iterable or conversion fails, leave as-is
                pass

        return True


def sanitize_log_message(message: Optional[str]) -> str:
    """
    Remove API keys and sensitive data from log messages.

    Sanitizes the following patterns:
    - OpenAI API keys (sk-*)
    - OpenRouter API keys (sk-or-*)
    - Anthropic API keys (sk-ant-*)
    - Bearer tokens
    - Other common API key patterns

    Args:
        message: The log message to sanitize

    Returns:
        str: Sanitized message with API keys replaced with [REDACTED-API-KEY]

    Example:
        >>> sanitize_log_message("Error with key sk-1234567890")
        'Error with key [REDACTED-API-KEY]'
    """
    if message is None:
        return ""

    if not isinstance(message, str):
        message = str(message)

    # Escape newlines/carriage returns to prevent log injection (CWE-117)
    sanitized = message.replace('\r\n', '\\r\\n').replace('\n', '\\n').replace('\r', '\\r')
    for pattern, replacement in API_KEY_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def setup_dual_logger(
    name: str = "spektiv",
    log_file: Optional[str] = None,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
) -> logging.Logger:
    """
    Setup a logger with dual output: terminal (Rich) + rotating file.

    Creates a logger that outputs to:
    1. Terminal with Rich formatting (if available) or standard StreamHandler
    2. Rotating file handler (5MB max size, 3 backups)

    Both handlers automatically sanitize API keys and sensitive data.

    Args:
        name: Logger name (default: "spektiv")
        log_file: Path to log file (default: logs/spektiv.log in results dir)
        console_level: Log level for terminal output (default: INFO)
        file_level: Log level for file output (default: DEBUG)

    Returns:
        logging.Logger: Configured logger instance

    Example:
        >>> logger = setup_dual_logger("my_module", "./logs/app.log")
        >>> logger.info("Terminal and file")
        >>> logger.debug("File only")
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Capture all levels, handlers will filter

    # Clear existing handlers to prevent duplicates
    logger.handlers.clear()

    # Create sanitizing filter
    sanitize_filter = SanitizingFilter()

    # ===== Terminal Handler =====
    if RICH_AVAILABLE:
        # Use Rich handler for beautiful terminal output
        console_handler = RichHandler(
            rich_tracebacks=True,
            show_time=True,
            show_path=False,
        )
    else:
        # Fall back to standard stream handler
        console_handler = logging.StreamHandler()

    console_handler.setLevel(console_level)
    console_handler.addFilter(sanitize_filter)

    # Console format (simpler for terminal)
    console_formatter = logging.Formatter(
        '%(message)s'
    )
    console_handler.setFormatter(console_formatter)

    logger.addHandler(console_handler)

    # ===== File Handler =====
    # Determine log file path
    if log_file is None:
        # Use TRADINGAGENTS_RESULTS_DIR or default to ./logs
        results_dir = os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results")
        log_dir = Path(results_dir) / "logs"
        log_file = str(log_dir / "spektiv.log")

    # Create log directory if it doesn't exist
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Create rotating file handler
    # 5MB max size, 3 backup files
    file_handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding='utf-8',
    )
    file_handler.setLevel(file_level)
    file_handler.addFilter(sanitize_filter)

    # File format (more detailed)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)

    logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger
