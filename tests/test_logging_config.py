import logging
import os
import tempfile
import pytest
from unittest.mock import patch


class TestLoggingConfigIntegration:
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        tradingagents_logger = logging.getLogger("tradingagents")
        for handler in tradingagents_logger.handlers[:]:
            tradingagents_logger.removeHandler(handler)
        tradingagents_logger.setLevel(logging.NOTSET)

        yield

        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        tradingagents_logger = logging.getLogger("tradingagents")
        for handler in tradingagents_logger.handlers[:]:
            tradingagents_logger.removeHandler(handler)

    def test_default_config_values_used_when_env_vars_not_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars_to_remove = [
                "TRADINGAGENTS_LOG_LEVEL",
                "TRADINGAGENTS_LOG_DIR",
                "TRADINGAGENTS_LOG_CONSOLE",
                "TRADINGAGENTS_LOG_FILE",
            ]
            clean_env = {k: v for k, v in os.environ.items() if k not in env_vars_to_remove}

            with patch.dict(os.environ, clean_env, clear=True):
                import importlib
                import tradingagents.logging as log_module
                importlib.reload(log_module)

                from tradingagents.default_config import DEFAULT_CONFIG

                expected_level = getattr(logging, DEFAULT_CONFIG.get("log_level", "INFO").upper())

                logger = log_module.setup_logging()

                assert logger.level == expected_level

    def test_env_vars_override_default_config_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "WARNING",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE": "false",
                "TRADINGAGENTS_LOG_FILE": "true",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                import importlib
                import tradingagents.logging as log_module
                importlib.reload(log_module)

                logger = log_module.setup_logging()

                assert logger.level == logging.WARNING

    def test_boolean_parsing_for_log_console_and_file(self):
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
                ("yes", True),
                ("no", False),
            ]

            for bool_str, expected in test_cases:
                env_vars = {
                    "TRADINGAGENTS_LOG_LEVEL": "INFO",
                    "TRADINGAGENTS_LOG_DIR": tmpdir,
                    "TRADINGAGENTS_LOG_CONSOLE": bool_str,
                    "TRADINGAGENTS_LOG_FILE": "false",
                }

                tradingagents_logger = logging.getLogger("tradingagents")
                for handler in tradingagents_logger.handlers[:]:
                    tradingagents_logger.removeHandler(handler)

                with patch.dict(os.environ, env_vars, clear=False):
                    import importlib
                    import tradingagents.logging as log_module
                    importlib.reload(log_module)

                    logger = log_module.setup_logging()

                    from rich.logging import RichHandler
                    has_rich_handler = any(isinstance(h, RichHandler) for h in logger.handlers)

                    assert has_rich_handler == expected, f"TRADINGAGENTS_LOG_CONSOLE={bool_str} should result in RichHandler present={expected}"

    def test_invalid_log_level_falls_back_to_info(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_vars = {
                "TRADINGAGENTS_LOG_LEVEL": "INVALID_LEVEL",
                "TRADINGAGENTS_LOG_DIR": tmpdir,
                "TRADINGAGENTS_LOG_CONSOLE": "false",
                "TRADINGAGENTS_LOG_FILE": "true",
            }
            with patch.dict(os.environ, env_vars, clear=False):
                import importlib
                import tradingagents.logging as log_module
                importlib.reload(log_module)

                logger = log_module.setup_logging()

                assert logger.level == logging.INFO, "Invalid log level should fall back to INFO"
