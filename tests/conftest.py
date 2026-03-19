"""Shared fixtures and markers for TradingAgents tests."""

import os
import pytest


_DEMO_KEY = "demo"


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: tests that hit real external APIs")
    config.addinivalue_line("markers", "slow: tests that take a long time to run")


@pytest.fixture(autouse=True)
def _set_alpha_vantage_demo_key(monkeypatch):
    """Ensure ALPHA_VANTAGE_API_KEY is always set to 'demo' unless the test
    overrides it.  This means no test needs its own patch.dict for the key."""
    if not os.environ.get("ALPHA_VANTAGE_API_KEY"):
        monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", _DEMO_KEY)


@pytest.fixture
def av_api_key():
    """Return the Alpha Vantage API key ('demo' by default).

    Skips the test automatically when the Alpha Vantage API endpoint is not
    reachable (e.g. sandboxed CI without outbound network access) or when
    the socket is blocked by pytest-socket.
    """
    import socket

    try:
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
            ("www.alphavantage.co", 443)
        )
    except (socket.error, OSError, RuntimeError):
        pytest.skip("Alpha Vantage API not reachable — skipping live API test")

    return os.environ.get("ALPHA_VANTAGE_API_KEY", _DEMO_KEY)


@pytest.fixture
def av_config():
    """Return a config dict with Alpha Vantage as the scanner data vendor."""
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    config["data_vendors"] = {
        **config["data_vendors"],
        "scanner_data": "alpha_vantage",
    }
    return config
