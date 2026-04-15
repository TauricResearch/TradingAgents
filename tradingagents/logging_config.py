"""Logging configuration for the TradingAgents framework.

This module provides structured logging setup for consistent log formatting
across all framework components.
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    name: str = "tradingagents",
) -> logging.Logger:
    """Configure logging for the trading agents framework.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional file path for log output.
        name: Logger name, defaults to 'tradingagents'.

    Returns:
        Configured logger instance.

    Example:
        >>> logger = setup_logging("DEBUG", Path("logs/trading.log"))
        >>> logger.info("Starting trading analysis")
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers = []

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Logger name (typically __name__ of the module).

    Returns:
        Logger instance.

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Module loaded")
    """
    return logging.getLogger(name)


class TradingAgentsLogger:
    """Context manager for logging trading operations.

    Provides structured logging with timing information for operations.

    Example:
        >>> with TradingAgentsLogger("market_analysis", "AAPL") as log:
        ...     # Perform analysis
        ...     log.info("Fetching market data")
    """

    def __init__(self, operation: str, symbol: str | None = None):
        """Initialize the logger context.

        Args:
            operation: Name of the operation being logged.
            symbol: Optional trading symbol being analyzed.
        """
        self.operation = operation
        self.symbol = symbol
        self.logger = get_logger(f"tradingagents.{operation}")
        self.start_time: datetime | None = None

    def __enter__(self) -> "TradingAgentsLogger":
        """Enter the logging context."""
        self.start_time = datetime.now(timezone.utc)
        msg = f"Starting {self.operation}"
        if self.symbol:
            msg += f" for {self.symbol}"
        self.logger.info(msg)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the logging context."""
        if self.start_time:
            duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()
            if exc_type:
                self.logger.error(
                    f"{self.operation} failed after {duration:.2f}s: {exc_val}"
                )
            else:
                self.logger.info(f"{self.operation} completed in {duration:.2f}s")

    def info(self, message: str):
        """Log an info message."""
        self.logger.info(message)

    def warning(self, message: str):
        """Log a warning message."""
        self.logger.warning(message)

    def error(self, message: str):
        """Log an error message."""
        self.logger.error(message)

    def debug(self, message: str):
        """Log a debug message."""
        self.logger.debug(message)
