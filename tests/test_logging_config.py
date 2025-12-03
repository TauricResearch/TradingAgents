import logging
import os
import tempfile
from unittest.mock import patch

import pytest

import tradingagents.logging as log_module


class TestLoggingConfigIntegration:
    def test_default_config_values_used_when_env_vars_not_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars_to_remove = [
                "TRADINGAGENTS_LOG_LEVEL",
                "TRADINGAGENTS_LOG_DIR",
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED",
                "TRADINGAGENTS_LOG_FILE_ENABLED",
            ]
            clean_env = {
                k: v for k, v in os.environ.items() if k not in env_vars_to_remove
            }

            with patch.dict(os.environ, clean_env, clear=True):
                from tradingagents.default_config import DEFAULT_CONFIG

                expected_level = getattr(
                    logging, DEFAULT_CONFIG.get("log_level", "INFO").upper()
                )

                logger = log_module.setup_logging()

                assert logger.level == expected_level

    def test_env_vars_override_default_config_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "WARNING",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED": "false",
                "TRADINGAGENTS_LOG_FILE_ENABLED": "true",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                logger = log_module.setup_logging()

                assert logger.level == logging.WARNING

    def test_boolean_parsing_for_log_console_and_file(self):
        from rich.logging import RichHandler

        from tradingagents import config as main_config

        with tempfile.TemporaryDirectory() as tmpdir:
            test_cases = [
                ("true", True),
                ("false", False),
                ("1", True),
                ("0", False),
                ("True", True),
                ("False", False),
                ("TRUE", True),
                ("FALSE", False),
            ]

            for bool_str, expected in test_cases:
                env_vars = {
                    "TRADINGAGENTS_LOG_LEVEL": "INFO",
                    "TRADINGAGENTS_LOG_DIR": tmpdir,
                    "TRADINGAGENTS_LOG_CONSOLE_ENABLED": bool_str,
                    "TRADINGAGENTS_LOG_FILE_ENABLED": "false",
                }

                tradingagents_logger = logging.getLogger("tradingagents")
                for handler in tradingagents_logger.handlers[:]:
                    tradingagents_logger.removeHandler(handler)
                log_module._logging_initialized = False
                main_config._settings = None

                with patch.dict(os.environ, env_vars, clear=False):
                    logger = log_module.setup_logging()

                    has_rich_handler = any(
                        isinstance(h, RichHandler) for h in logger.handlers
                    )

                    assert (
                        has_rich_handler == expected
                    ), f"TRADINGAGENTS_LOG_CONSOLE_ENABLED={bool_str} should result in RichHandler present={expected}"

    def test_invalid_log_level_raises_validation_error(self):
        from pydantic import ValidationError

        from tradingagents import config as main_config

        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "INVALID_LEVEL",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE_ENABLED": "false",
                "TRADINGAGENTS_LOG_FILE_ENABLED": "true",
            }
            main_config._settings = None

            with patch.dict(os.environ, env_vars, clear=False):
                with pytest.raises(ValidationError) as exc_info:
                    log_module.setup_logging()

                assert "log_level" in str(exc_info.value)
