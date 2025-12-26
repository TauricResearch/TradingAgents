"""
Shared pytest fixtures for unit API tests.

This module imports fixtures from the main API conftest
to make them available to unit tests.
"""

import pytest

# Import all fixtures from main API conftest
pytest_plugins = ["tests.api.conftest"]
