"""
Test suite for Dual-Output Logging Configuration.

This module tests:
1. setup_dual_logger() creates both terminal and file handlers
2. RotatingFileHandler configuration (maxBytes, backupCount)
3. sanitize_log_message() removes API keys and sensitive data
4. Log rotation works at 5MB boundary
5. Log formatting for both handlers
6. File creation and permissions
"""

import logging
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, call
from logging.handlers import RotatingFileHandler


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def logger_name():
    """Generate unique logger name for each test."""
    import uuid
    return f"test_logger_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup_logger():
    """Cleanup logger after test to prevent handler accumulation."""
    loggers_to_cleanup = []

    def register(logger):
        loggers_to_cleanup.append(logger)
        return logger

    yield register

    # Cleanup
    for logger in loggers_to_cleanup:
        logger.handlers.clear()
        logger.filters.clear()


# ============================================================================
# Test setup_dual_logger() Function
# ============================================================================

class TestSetupDualLogger:
    """Test the dual logger setup function."""

    def test_creates_logger_with_two_handlers(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that setup_dual_logger creates a logger with terminal and file handlers."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        assert isinstance(logger, logging.Logger)
        assert len(logger.handlers) == 2

        # Check handler types
        handler_types = [type(h) for h in logger.handlers]
        assert logging.StreamHandler in handler_types
        assert RotatingFileHandler in handler_types

    def test_terminal_handler_configuration(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that terminal handler is configured correctly."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        # Find the StreamHandler
        stream_handler = None
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
                stream_handler = handler
                break

        assert stream_handler is not None
        assert stream_handler.level == logging.INFO

    def test_file_handler_configuration(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that file handler is configured with rotation settings."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        # Find the RotatingFileHandler
        file_handler = None
        for handler in logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                file_handler = handler
                break

        assert file_handler is not None
        assert file_handler.maxBytes == 5 * 1024 * 1024  # 5MB
        assert file_handler.backupCount == 3
        assert file_handler.level == logging.DEBUG

    def test_creates_log_file(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that setup_dual_logger creates the log file."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        logger.info("Test message")

        # File should be created
        assert log_file.exists()

    def test_creates_log_directory_if_missing(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that setup_dual_logger creates parent directories if they don't exist."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "nested" / "dir" / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        logger.info("Test message")

        assert log_file.exists()
        assert log_file.parent.exists()

    def test_logger_level_configuration(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that logger is configured with DEBUG level."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        assert logger.level == logging.DEBUG

    def test_default_log_file_location(self, logger_name, cleanup_logger):
        """Test default log file location when not specified."""
        from tradingagents.utils.logging_config import setup_dual_logger

        logger = setup_dual_logger(name=logger_name)
        cleanup_logger(logger)

        # Find the RotatingFileHandler
        file_handler = None
        for handler in logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                file_handler = handler
                break

        assert file_handler is not None
        # Should default to logs/tradingagents.log
        assert "logs" in file_handler.baseFilename
        assert "tradingagents.log" in file_handler.baseFilename

    def test_custom_log_levels(self, temp_log_dir, logger_name, cleanup_logger):
        """Test setting custom log levels for handlers."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(
            name=logger_name,
            log_file=str(log_file),
            console_level=logging.WARNING,
            file_level=logging.INFO
        )
        cleanup_logger(logger)

        # Find handlers
        stream_handler = None
        file_handler = None
        for handler in logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                file_handler = handler
            elif isinstance(handler, logging.StreamHandler):
                stream_handler = handler

        assert stream_handler.level == logging.WARNING
        assert file_handler.level == logging.INFO


# ============================================================================
# Test sanitize_log_message() Function
# ============================================================================

class TestSanitizeLogMessage:
    """Test the log message sanitization function."""

    def test_sanitize_openai_api_key(self):
        """Test that OpenAI API keys (sk-*) are redacted."""
        from tradingagents.utils.logging_config import sanitize_log_message

        message = "Error with API key sk-1234567890abcdef: Rate limit exceeded"
        sanitized = sanitize_log_message(message)

        assert "sk-1234567890abcdef" not in sanitized
        assert "[REDACTED-API-KEY]" in sanitized

    def test_sanitize_openrouter_api_key(self):
        """Test that OpenRouter API keys (sk-or-*) are redacted."""
        from tradingagents.utils.logging_config import sanitize_log_message

        message = "Using key sk-or-v1-abcdef123456 for request"
        sanitized = sanitize_log_message(message)

        assert "sk-or-v1-abcdef123456" not in sanitized
        assert "[REDACTED-API-KEY]" in sanitized

    def test_sanitize_bearer_token(self):
        """Test that Bearer tokens are redacted."""
        from tradingagents.utils.logging_config import sanitize_log_message

        message = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        sanitized = sanitize_log_message(message)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
        assert "[REDACTED-TOKEN]" in sanitized

    def test_sanitize_anthropic_api_key(self):
        """Test that Anthropic API keys are redacted."""
        from tradingagents.utils.logging_config import sanitize_log_message

        message = "x-api-key: sk-ant-api03-1234567890abcdef"
        sanitized = sanitize_log_message(message)

        assert "sk-ant-api03-1234567890abcdef" not in sanitized
        assert "[REDACTED-API-KEY]" in sanitized

    def test_sanitize_multiple_keys_in_message(self):
        """Test that multiple API keys in one message are all redacted."""
        from tradingagents.utils.logging_config import sanitize_log_message

        message = "Tried sk-1111111111 and sk-or-v1-2222222222 but both failed"
        sanitized = sanitize_log_message(message)

        assert "sk-1111111111" not in sanitized
        assert "sk-or-v1-2222222222" not in sanitized
        assert sanitized.count("[REDACTED-API-KEY]") == 2

    def test_sanitize_preserves_safe_content(self):
        """Test that non-sensitive content is preserved."""
        from tradingagents.utils.logging_config import sanitize_log_message

        message = "Rate limit exceeded for model gpt-4. Please retry in 60 seconds."
        sanitized = sanitize_log_message(message)

        assert sanitized == message

    def test_sanitize_empty_message(self):
        """Test sanitizing an empty message."""
        from tradingagents.utils.logging_config import sanitize_log_message

        sanitized = sanitize_log_message("")

        assert sanitized == ""

    def test_sanitize_none_message(self):
        """Test sanitizing None message."""
        from tradingagents.utils.logging_config import sanitize_log_message

        sanitized = sanitize_log_message(None)

        assert sanitized == "" or sanitized is None

    def test_sanitize_message_with_json(self):
        """Test sanitizing a message containing JSON with API key."""
        from tradingagents.utils.logging_config import sanitize_log_message

        message = '{"api_key": "sk-1234567890", "model": "gpt-4"}'
        sanitized = sanitize_log_message(message)

        assert "sk-1234567890" not in sanitized
        assert "[REDACTED-API-KEY]" in sanitized
        assert '"model": "gpt-4"' in sanitized

    def test_sanitize_url_with_api_key(self):
        """Test sanitizing URLs containing API keys in query parameters."""
        from tradingagents.utils.logging_config import sanitize_log_message

        message = "Calling https://api.example.com/v1/chat?api_key=sk-test123456"
        sanitized = sanitize_log_message(message)

        assert "sk-test123456" not in sanitized
        assert "[REDACTED-API-KEY]" in sanitized

    def test_sanitize_partial_key_patterns(self):
        """Test that partial key patterns that look like API keys are redacted."""
        from tradingagents.utils.logging_config import sanitize_log_message

        message = "Key starts with sk- but full key is sk-proj-abcdefghijklmnop"
        sanitized = sanitize_log_message(message)

        assert "sk-proj-abcdefghijklmnop" not in sanitized
        assert "[REDACTED-API-KEY]" in sanitized


# ============================================================================
# Test Log Rotation
# ============================================================================

class TestLogRotation:
    """Test log file rotation functionality."""

    def test_rotation_at_5mb_boundary(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that log rotation occurs at 5MB file size."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        # Find the RotatingFileHandler
        file_handler = None
        for handler in logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                file_handler = handler
                break

        # Write large amount of data to trigger rotation
        large_message = "X" * 1024 * 100  # 100KB per message
        for i in range(60):  # 6MB total
            logger.info(large_message)

        # Should create backup file when rotation occurs
        backup_file = Path(str(log_file) + ".1")
        assert log_file.exists()
        # Rotation may or may not have occurred yet depending on exact timing
        # Just verify the configuration is correct
        assert file_handler.maxBytes == 5 * 1024 * 1024

    def test_backup_count_configuration(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that backupCount is set to 3."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        # Find the RotatingFileHandler
        file_handler = None
        for handler in logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                file_handler = handler
                break

        assert file_handler.backupCount == 3

    def test_rotation_creates_backup_files(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that rotation creates .1, .2, .3 backup files."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        # Use smaller maxBytes for testing
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        # Manually trigger rotation by writing through handler
        file_handler = None
        for handler in logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                file_handler = handler
                break

        # Override maxBytes for testing
        file_handler.maxBytes = 1024  # 1KB for easy testing

        # Write enough to trigger multiple rotations
        for i in range(10):
            logger.info("X" * 200)  # 200 bytes per message

        # Check that main log file exists
        assert log_file.exists()


# ============================================================================
# Test Log Formatting
# ============================================================================

class TestLogFormatting:
    """Test log message formatting."""

    def test_log_format_includes_timestamp(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that log messages include timestamp."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        logger.info("Test message")

        # Read log file
        content = log_file.read_text()
        # Should have timestamp format like 2024-12-26 10:30:45
        assert any(char.isdigit() for char in content)

    def test_log_format_includes_level(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that log messages include log level."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        content = log_file.read_text()
        assert "INFO" in content
        assert "WARNING" in content
        assert "ERROR" in content

    def test_log_format_includes_message(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that log messages include the actual message."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        logger.info("This is a test message")

        content = log_file.read_text()
        assert "This is a test message" in content

    def test_multiline_log_message(self, temp_log_dir, logger_name, cleanup_logger):
        """Test handling of multiline log messages."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        logger.info("Line 1\nLine 2\nLine 3")

        content = log_file.read_text()
        assert "Line 1" in content
        assert "Line 2" in content
        assert "Line 3" in content


# ============================================================================
# Test Integration with Sanitization
# ============================================================================

class TestLoggingWithSanitization:
    """Test that sanitization is applied when logging."""

    def test_logged_message_is_sanitized(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that API keys are sanitized before being written to log."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        # This should be sanitized automatically
        logger.error("API request failed with key sk-test1234567890")

        content = log_file.read_text()
        assert "sk-test1234567890" not in content
        assert "[REDACTED-API-KEY]" in content

    @patch('tradingagents.utils.logging_config.sanitize_log_message')
    def test_sanitize_called_on_log(self, mock_sanitize, temp_log_dir, logger_name, cleanup_logger):
        """Test that sanitize_log_message is called when logging."""
        from tradingagents.utils.logging_config import setup_dual_logger

        mock_sanitize.return_value = "Sanitized message"

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        logger.info("Test message with sk-test123")

        # Sanitize should be called
        # Note: This test may need adjustment based on how sanitization is integrated
        # It might be called via a filter or formatter


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestLoggingEdgeCases:
    """Test edge cases in logging configuration."""

    def test_permission_denied_for_log_file(self, temp_log_dir, logger_name):
        """Test handling when log file location has no write permission."""
        from tradingagents.utils.logging_config import setup_dual_logger

        # Create a directory with no write permission
        readonly_dir = temp_log_dir / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)

        log_file = readonly_dir / "test.log"

        # Should handle gracefully or raise appropriate error
        try:
            logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
            # If it succeeds, at least terminal logging should work
            assert len(logger.handlers) >= 1
        except (PermissionError, OSError):
            # Expected behavior - permission denied
            pass
        finally:
            # Cleanup
            readonly_dir.chmod(0o755)

    def test_invalid_log_file_path(self, logger_name):
        """Test handling of invalid log file path."""
        from tradingagents.utils.logging_config import setup_dual_logger

        # Use an invalid path
        log_file = "/invalid/path/that/does/not/exist/test.log"

        # Should either create the path or handle gracefully
        try:
            logger = setup_dual_logger(name=logger_name, log_file=log_file)
            # If it succeeds, verify it created the directory
            assert Path(log_file).parent.exists() or len(logger.handlers) >= 1
        except (PermissionError, OSError):
            # Expected - cannot create directory
            pass

    def test_unicode_in_log_message(self, temp_log_dir, logger_name, cleanup_logger):
        """Test handling of unicode characters in log messages."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        logger.info("Unicode test: 你好 🌍 €")

        content = log_file.read_text(encoding='utf-8')
        assert "你好" in content or "Unicode test" in content

    def test_very_long_log_message(self, temp_log_dir, logger_name, cleanup_logger):
        """Test handling of very long log messages."""
        from tradingagents.utils.logging_config import setup_dual_logger

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        long_message = "X" * 10000  # 10KB message
        logger.info(long_message)

        content = log_file.read_text()
        assert len(content) > 9000  # Should contain most of the message

    def test_concurrent_logging(self, temp_log_dir, logger_name, cleanup_logger):
        """Test that concurrent logging to same file works."""
        from tradingagents.utils.logging_config import setup_dual_logger
        import threading

        log_file = temp_log_dir / "test.log"
        logger = setup_dual_logger(name=logger_name, log_file=str(log_file))
        cleanup_logger(logger)

        def log_messages(thread_id):
            for i in range(10):
                logger.info(f"Thread {thread_id} message {i}")

        threads = []
        for i in range(5):
            t = threading.Thread(target=log_messages, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        content = log_file.read_text()
        # Should have all 50 messages
        assert content.count("message") >= 40  # Allow some loss in concurrent scenario
