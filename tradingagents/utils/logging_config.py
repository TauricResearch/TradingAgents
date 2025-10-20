"""
Comprehensive Logging Configuration for TradingAgents

This module provides a centralized logging system with:
- Multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- File and console logging
- Log rotation to prevent huge files
- Structured logging with context
- Component-specific loggers
- Performance tracking
- API call tracking
"""

import logging
import logging.handlers
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import json


class StructuredFormatter(logging.Formatter):
    """Custom formatter that adds structured context to log messages."""

    def format(self, record: logging.LogRecord) -> str:
        # Add timestamp
        record.timestamp = datetime.now(timezone.utc).isoformat()

        # Add component info
        if not hasattr(record, "component"):
            record.component = record.name.split(".")[-1]

        # Format the message
        formatted = super().format(record)

        # Add context if available
        if hasattr(record, "context") and record.context:
            context_str = json.dumps(record.context, indent=2)
            formatted = f"{formatted}\n  Context: {context_str}"

        return formatted


class TradingAgentsLogger:
    """Main logger class for TradingAgents application."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)

        # Create different log files for different purposes
        self.log_files = {
            "main": self.log_dir / "tradingagents.log",
            "api": self.log_dir / "api_calls.log",
            "memory": self.log_dir / "memory.log",
            "agents": self.log_dir / "agents.log",
            "errors": self.log_dir / "errors.log",
            "performance": self.log_dir / "performance.log",
        }

        # Configure root logger
        self._configure_root_logger()

        self._initialized = True

    def _configure_root_logger(self):
        """Configure the root logger with handlers and formatters."""
        root_logger = logging.getLogger("tradingagents")
        root_logger.setLevel(logging.DEBUG)

        # Remove existing handlers to avoid duplicates
        root_logger.handlers.clear()

        # Console handler (INFO and above)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = StructuredFormatter(
            "%(asctime)s | %(levelname)-8s | %(component)-15s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

        # Main file handler (DEBUG and above) with rotation
        main_handler = logging.handlers.RotatingFileHandler(
            self.log_files["main"],
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        main_handler.setLevel(logging.DEBUG)
        main_formatter = StructuredFormatter(
            "%(timestamp)s | %(levelname)-8s | %(name)s | %(component)s | %(message)s"
        )
        main_handler.setFormatter(main_formatter)
        root_logger.addHandler(main_handler)

        # Error file handler (ERROR and above only)
        error_handler = logging.handlers.RotatingFileHandler(
            self.log_files["errors"], maxBytes=5 * 1024 * 1024, backupCount=3
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(main_formatter)
        root_logger.addHandler(error_handler)

    def get_logger(self, name: str, component: Optional[str] = None) -> logging.Logger:
        """
        Get a logger for a specific component.

        Args:
            name: Logger name (e.g., 'tradingagents.memory')
            component: Component name for logging context

        Returns:
            Configured logger instance
        """
        logger = logging.getLogger(name)

        # Add component as a filter if provided
        if component:

            class ComponentFilter(logging.Filter):
                def filter(self, record):
                    record.component = component
                    return True

            logger.addFilter(ComponentFilter())

        return logger

    def add_file_handler(
        self, logger_name: str, filename: str, level: int = logging.DEBUG
    ):
        """Add a dedicated file handler to a specific logger."""
        logger = logging.getLogger(logger_name)
        handler = logging.handlers.RotatingFileHandler(
            self.log_dir / filename, maxBytes=10 * 1024 * 1024, backupCount=3
        )
        handler.setLevel(level)
        formatter = StructuredFormatter(
            "%(timestamp)s | %(levelname)-8s | %(component)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)


class APICallLogger:
    """Logger specifically for tracking API calls and costs."""

    def __init__(self):
        self.logger = get_logger("tradingagents.api", component="API")
        self.call_count = 0
        self.total_tokens = 0

    def log_call(
        self,
        provider: str,
        model: str,
        endpoint: str,
        tokens: Optional[int] = None,
        cost: Optional[float] = None,
        duration: Optional[float] = None,
        status: str = "success",
        error: Optional[str] = None,
    ):
        """Log an API call with details."""
        self.call_count += 1
        if tokens:
            self.total_tokens += tokens

        context = {
            "call_number": self.call_count,
            "provider": provider,
            "model": model,
            "endpoint": endpoint,
            "tokens": tokens,
            "cost": cost,
            "duration_ms": duration,
            "status": status,
        }

        if error:
            context["error"] = error
            self.logger.error(f"API call failed: {error}", extra={"context": context})
        else:
            self.logger.info(
                f"API call to {provider}/{model} - {status}", extra={"context": context}
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get API call statistics."""
        return {"total_calls": self.call_count, "total_tokens": self.total_tokens}


class PerformanceLogger:
    """Logger for tracking performance metrics."""

    def __init__(self):
        self.logger = get_logger("tradingagents.performance", component="PERF")
        self.timings = {}

    def log_timing(
        self, operation: str, duration: float, context: Optional[Dict] = None
    ):
        """Log operation timing."""
        if operation not in self.timings:
            self.timings[operation] = []
        self.timings[operation].append(duration)

        log_context = {"operation": operation, "duration_ms": duration}
        if context:
            log_context.update(context)

        self.logger.info(
            f"{operation} completed in {duration:.2f}ms", extra={"context": log_context}
        )

    def get_average_timing(self, operation: str) -> Optional[float]:
        """Get average timing for an operation."""
        if operation in self.timings and self.timings[operation]:
            return sum(self.timings[operation]) / len(self.timings[operation])
        return None

    def log_summary(self):
        """Log performance summary."""
        summary = {}
        for operation, timings in self.timings.items():
            if timings:
                summary[operation] = {
                    "count": len(timings),
                    "avg_ms": sum(timings) / len(timings),
                    "min_ms": min(timings),
                    "max_ms": max(timings),
                }

        self.logger.info("Performance Summary", extra={"context": summary})


# Singleton instances
_logger_instance = None
_api_logger_instance = None
_perf_logger_instance = None


def get_logger(
    name: str = "tradingagents", component: Optional[str] = None
) -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name
        component: Component name for context

    Returns:
        Logger instance
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = TradingAgentsLogger()

    return _logger_instance.get_logger(name, component)


def get_api_logger() -> APICallLogger:
    """Get the API call logger instance."""
    global _api_logger_instance
    if _api_logger_instance is None:
        _api_logger_instance = APICallLogger()
    return _api_logger_instance


def get_performance_logger() -> PerformanceLogger:
    """Get the performance logger instance."""
    global _perf_logger_instance
    if _perf_logger_instance is None:
        _perf_logger_instance = PerformanceLogger()
    return _perf_logger_instance


def set_log_level(level: str):
    """
    Set the global log level.

    Args:
        level: Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    """
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    log_level = level_map.get(level.upper(), logging.INFO)
    logging.getLogger("tradingagents").setLevel(log_level)


def configure_logging(
    level: str = "INFO", log_dir: Optional[str] = None, console: bool = True
):
    """
    Configure the logging system.

    Args:
        level: Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        log_dir: Directory for log files (default: 'logs')
        console: Whether to log to console
    """
    global _logger_instance

    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Initialize logger
    if _logger_instance is None:
        _logger_instance = TradingAgentsLogger()

    # Set log level
    set_log_level(level)

    # Configure console logging
    root_logger = logging.getLogger("tradingagents")
    if not console:
        # Remove console handler
        root_logger.handlers = [
            h for h in root_logger.handlers if not isinstance(h, logging.StreamHandler)
        ]


# Initialize on import
_logger_instance = TradingAgentsLogger()


if __name__ == "__main__":
    # Test the logging system
    print("Testing TradingAgents Logging System")
    print("=" * 70)

    # Get loggers
    main_logger = get_logger("tradingagents.test", component="TEST")
    api_logger = get_api_logger()
    perf_logger = get_performance_logger()

    # Test different log levels
    main_logger.debug("This is a debug message")
    main_logger.info("This is an info message")
    main_logger.warning("This is a warning message")
    main_logger.error("This is an error message")

    # Test API logging
    api_logger.log_call(
        provider="openai",
        model="gpt-4",
        endpoint="/v1/chat/completions",
        tokens=150,
        cost=0.003,
        duration=250.5,
        status="success",
    )

    api_logger.log_call(
        provider="openrouter",
        model="llama-3",
        endpoint="/v1/chat/completions",
        status="error",
        error="Connection timeout",
    )

    # Test performance logging
    perf_logger.log_timing("analyst_execution", 1234.5, {"analyst": "market"})
    perf_logger.log_timing("analyst_execution", 987.3, {"analyst": "news"})
    perf_logger.log_summary()

    print("\n" + "=" * 70)
    print("Logging test complete. Check the 'logs' directory for output files.")
    print("API Call Stats:", api_logger.get_stats())
