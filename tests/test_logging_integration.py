import json
import logging
import os
import tempfile
from unittest.mock import patch

import tradingagents.logging as log_module


class TestLoggingIntegration:
    def test_logging_initialization_from_module_import(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "INFO",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED": "false",
                "TRADINGAGENTS_LOG_FILE_ENABLED": "true",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                log_module.setup_logging()

                interface_logger = log_module.get_logger(
                    "tradingagents.dataflows.interface"
                )

                assert interface_logger is not None
                assert interface_logger.name == "tradingagents.dataflows.interface"

                interface_logger.info("Test message from interface logger")

                log_file = os.path.join(tmpdir, "tradingagents.log")
                assert os.path.exists(log_file)

                with open(log_file) as f:
                    content = f.read()
                    assert "Test message from interface logger" in content

    def test_rich_handler_does_not_break_cli_live_displays(self):
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

                rich_handlers = [
                    h for h in logger.handlers if isinstance(h, RichHandler)
                ]
                assert len(rich_handlers) == 1

                rich_handler = rich_handlers[0]
                assert rich_handler.console is not None
                assert rich_handler.console.file is not None

    def test_log_file_creation_and_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "DEBUG",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED": "false",
                "TRADINGAGENTS_LOG_FILE_ENABLED": "true",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                logger = log_module.setup_logging()

                logger.debug("Debug message")
                logger.info("Info message")
                logger.warning("Warning message")
                logger.error("Error message")

                for handler in logger.handlers:
                    handler.flush()

                log_file = os.path.join(tmpdir, "tradingagents.log")
                assert os.path.exists(log_file)

                with open(log_file) as f:
                    lines = f.readlines()

                assert len(lines) >= 4

                for line in lines:
                    log_entry = json.loads(line)
                    assert "timestamp" in log_entry
                    assert "level" in log_entry
                    assert "logger" in log_entry
                    assert "message" in log_entry

    def test_logger_hierarchy_inherits_parent_configuration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "WARNING",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED": "false",
                "TRADINGAGENTS_LOG_FILE_ENABLED": "true",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                root_logger = log_module.setup_logging()

                child_logger = log_module.get_logger(
                    "tradingagents.dataflows.interface"
                )
                grandchild_logger = log_module.get_logger(
                    "tradingagents.dataflows.interface.submodule"
                )

                assert root_logger.level == logging.WARNING

                child_logger.info("This should not be logged")
                child_logger.warning("This should be logged")

                for handler in root_logger.handlers:
                    handler.flush()

                log_file = os.path.join(tmpdir, "tradingagents.log")
                with open(log_file) as f:
                    content = f.read()

                assert "This should not be logged" not in content
                assert "This should be logged" in content

    def test_lazy_initialization_pattern(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "INFO",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED": "false",
                "TRADINGAGENTS_LOG_FILE_ENABLED": "true",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                log_module._logging_initialized = False

                logger = log_module.get_logger("tradingagents.test")

                assert log_module._logging_initialized is True
                assert logger is not None
