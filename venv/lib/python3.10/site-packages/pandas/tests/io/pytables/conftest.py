import uuid

import pytest


@pytest.fixture
def setup_path():
    """Fixture for setup path"""
    return f"tmp.__{uuid.uuid4()}__.h5"
