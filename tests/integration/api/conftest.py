"""
Shared pytest fixtures for integration API tests.

This module imports fixtures from the main API conftest
to make them available to integration tests.
"""

import pytest

# Import all fixtures from main API conftest
pytest_plugins = ["tests.api.conftest"]
