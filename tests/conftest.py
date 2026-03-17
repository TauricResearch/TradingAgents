"""Shared fixtures and markers for TradingAgents tests."""

import os
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: tests that hit real external APIs")
    config.addinivalue_line("markers", "slow: tests that take a long time to run")


@pytest.fixture
def av_api_key():
    """Return the Alpha Vantage API key or skip the test."""
    key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not key:
        pytest.skip("ALPHA_VANTAGE_API_KEY not set")
    return key


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
