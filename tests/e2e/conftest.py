"""E2E test configuration — real LLM API calls, manual trigger only."""

import pytest


def pytest_collection_modifyitems(config, items):
    """Mark all e2e tests as slow."""
    for item in items:
        item.add_marker(pytest.mark.e2e)
        item.add_marker(pytest.mark.slow)
