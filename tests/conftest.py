"""Shared pytest fixtures that prevent CI hangs when API keys are absent."""

import os
import socket
from pathlib import Path

import pytest


def _suite_temp_root() -> Path:
    """Create a temp root entirely outside the user's home for the suite.

    Some libraries (notably yfinance) create cache directories under the OS temp
    root. On Windows the default temp root often lives under the user profile,
    which violates the suite isolation contract before any test runs.
    """
    if os.name == "nt":
        root = Path(Path.home().anchor) / "tradingagents-suite-tmp"
    else:
        root = Path("/tmp/tradingagents-suite-tmp")
    root.mkdir(exist_ok=True, parents=True)
    os.environ["TMPDIR"] = str(root)
    os.environ["TEMP"] = str(root)
    os.environ["TMP"] = str(root)
    return root


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


def _own_file_locations():
    """Keep the suite's results, cache and memory log in a directory of its own.

    Set before the package is imported, whose defaults put them in the user's
    home: a test reading the user's cache would see what their runs fetched.
    """
    import tempfile

    root = _suite_temp_root()
    home = tempfile.mkdtemp(prefix="tradingagents-tests-", dir=root)
    os.environ["TRADINGAGENTS_RESULTS_DIR"] = os.path.join(home, "logs")
    os.environ["TRADINGAGENTS_CACHE_DIR"] = os.path.join(home, "cache")
    os.environ["TRADINGAGENTS_MEMORY_LOG_PATH"] = os.path.join(home, "memory", "trading_memory.md")


_own_file_locations()


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")
    # yfinance caches each symbol's time zone on disk, in the home directory
    # by default; the suite keeps it in a directory of its own.
    import tempfile

    import yfinance

    root = _suite_temp_root()
    yfinance.set_tz_cache_location(tempfile.mkdtemp(prefix="tradingagents-tests-yf-", dir=root))


@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    """Tests do not reach the network; one that must is marked integration."""
    if request.node.get_closest_marker("integration"):
        return

    def refuse(*args, **kwargs):
        raise OSError(f"test tried to reach the network: {args[1:] or kwargs}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: refuse(None, *a))
    # yfinance's HTTP client is libcurl, which never touches Python's sockets.
    from curl_cffi import requests as curl_requests

    monkeypatch.setattr(curl_requests.Session, "request", refuse)
    monkeypatch.setattr(curl_requests.AsyncSession, "request", refuse)


@pytest.fixture(autouse=True)
def _at_a_terminal(monkeypatch):
    """Tests of the interactive steps run as if at a terminal; pytest's stdin is
    not one. A test of an unattended run sets isatty to False itself."""
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)


@pytest.fixture(autouse=True)
def _own_cli_prefs(tmp_path, monkeypatch):
    """The CLI keeps the last run's selections in the user's home; tests keep theirs apart."""
    monkeypatch.setattr("cli.prefs._PREFS_PATH", tmp_path / "cli_prefs.json")


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
