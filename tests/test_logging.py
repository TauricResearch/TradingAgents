import json
import logging
import os
import tempfile
from unittest.mock import patch

import tradingagents.logging as log_module


class TestLoggingModule:
    def test_setup_logging_initializes_handlers_based_on_env_vars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "DEBUG",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED": "false",
                "TRADINGAGENTS_LOG_FILE_ENABLED": "true",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                root_logger = log_module.setup_logging()

                assert root_logger is not None
                assert root_logger.name == "tradingagents"
                assert root_logger.level == logging.DEBUG

                has_file_handler = any(
                    hasattr(h, "baseFilename") for h in root_logger.handlers
                )
                assert (
                    has_file_handler
                ), "File handler should be present when LOG_FILE=true"

    def test_get_logger_returns_properly_configured_logger_with_hierarchy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "INFO",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED": "false",
                "TRADINGAGENTS_LOG_FILE_ENABLED": "true",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                log_module.setup_logging()
                child_logger = log_module.get_logger(
                    "tradingagents.dataflows.interface"
                )

                assert child_logger.name == "tradingagents.dataflows.interface"
                assert (
                    child_logger.parent.name == "tradingagents.dataflows"
                    or child_logger.parent.name == "tradingagents"
                )

    def test_json_file_handler_writes_valid_json_with_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "DEBUG",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED": "false",
                "TRADINGAGENTS_LOG_FILE_ENABLED": "true",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                logger = log_module.setup_logging()
                logger.info("Test message for JSON validation")

                for handler in logger.handlers:
                    handler.flush()

                log_file_path = os.path.join(tmpdir, "tradingagents.log")
                assert os.path.exists(
                    log_file_path
                ), f"Log file should exist at {log_file_path}"

                with open(log_file_path) as f:
                    log_content = f.read().strip()

                assert log_content, "Log file should not be empty"

                log_entry = json.loads(log_content.split("\n")[0])

                required_fields = [
                    "timestamp",
                    "level",
                    "logger",
                    "message",
                    "filename",
                    "funcName",
                    "lineno",
                ]
                for field in required_fields:
                    assert (
                        field in log_entry
                    ), f"JSON log should contain '{field}' field"

                assert (
                    "T" in log_entry["timestamp"]
                ), "Timestamp should be in ISO 8601 format"
                assert log_entry["level"] == "INFO"
                assert log_entry["message"] == "Test message for JSON validation"

    def test_log_rotation_triggers_at_configured_file_size(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "DEBUG",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED": "false",
                "TRADINGAGENTS_LOG_FILE_ENABLED": "true",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                logger = log_module.setup_logging()

                file_handler = None
                for handler in logger.handlers:
                    if hasattr(handler, "maxBytes"):
                        file_handler = handler
                        break

                assert (
                    file_handler is not None
                ), "RotatingFileHandler should be configured"
                assert (
                    file_handler.maxBytes == 10 * 1024 * 1024
                ), "Max file size should be 10MB"
                assert file_handler.backupCount == 5, "Backup count should be 5"

    def test_console_handler_disabled_when_env_var_false(self):
        from tradingagents import config as main_config

        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "INFO",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED": "false",
                "TRADINGAGENTS_LOG_FILE_ENABLED": "true",
            }
            main_config._settings = None

            with patch.dict(os.environ, env_vars, clear=False):
                logger = log_module.setup_logging()

                from rich.logging import RichHandler

                has_rich_handler = any(
                    isinstance(h, RichHandler) for h in logger.handlers
                )
                assert (
                    not has_rich_handler
                ), "RichHandler should NOT be present when LOG_CONSOLE=false"

    def test_console_handler_enabled_when_env_var_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "INFO",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED": "true",
                "TRADINGAGENTS_LOG_FILE_ENABLED": "false",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                logger = log_module.setup_logging()

                from rich.logging import RichHandler

                has_rich_handler = any(
                    isinstance(h, RichHandler) for h in logger.handlers
                )
                assert (
                    has_rich_handler
                ), "RichHandler should be present when LOG_CONSOLE=true"
