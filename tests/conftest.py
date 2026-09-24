"""Shared pytest fixtures that prevent CI hangs when API keys are absent."""

import os
import socket

import pytest


def _blank_settings_overlay():
    """Blank every TRADINGAGENTS_* setting before the package is imported.

    The package loads .env on import and folds these variables into
    DEFAULT_CONFIG, so a contributor's own settings would become the defaults
    the suite asserts on. A blank value is still present, so load_dotenv leaves
    it alone, and the overlay reads it as unset. Tests of the overlay set their own.
    """
    from dotenv import dotenv_values, find_dotenv

    names = set(os.environ)
    for filename in (".env", ".env.enterprise"):
        names |= set(dotenv_values(find_dotenv(filename, usecwd=True)))
    for name in names:
        if name.startswith("TRADINGAGENTS_"):
            os.environ[name] = ""


_blank_settings_overlay()


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")


@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    """Tests do not reach the network; one that must is marked integration."""
    if request.node.get_closest_marker("integration"):
        return

    def refuse(self, address):
        raise OSError(f"test tried to reach the network: {address}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


_API_KEY_ENV_VARS = (
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_CN_API_KEY",
    "ZHIPU_API_KEY",
    "ZHIPU_CN_API_KEY",
    "MINIMAX_API_KEY",
    "MINIMAX_CN_API_KEY",
    "OPENROUTER_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
)


@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    for env_var in _API_KEY_ENV_VARS:
        # `or` not a .get default: an env var present but empty (e.g. a key left
        # blank in a .env copied from .env.example) must still get the placeholder.
        monkeypatch.setenv(env_var, os.environ.get(env_var) or "placeholder")


@pytest.fixture(autouse=True)
def _isolate_config():
    """Reset the global dataflows config before and after each test.

    ``set_config`` merges (it never clears keys absent from the override), so a
    test that sets e.g. ``tool_vendors`` would otherwise leak into later tests
    and make routing behavior order-dependent. Replace the global outright so
    every test starts from a clean DEFAULT_CONFIG.
    """
    import copy

    import tradingagents.dataflows.config as config_module
    import tradingagents.default_config as default_config

    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    yield
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
