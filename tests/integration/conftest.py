"""Integration test configuration — VCR cassette replay for data API tests."""

import os
import pytest


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "cassette_library_dir": "tests/cassettes",
        "record_mode": "none",
        "match_on": ["method", "scheme", "host", "port", "path"],
        "filter_headers": [
            "Authorization",
            "Cookie",
            "X-Api-Key",
        ],
        "filter_query_parameters": [
            "apikey",
            "token",
        ],
        "decode_compressed_response": True,
    }


@pytest.fixture
def av_api_key():
    """Return the Alpha Vantage API key for integration tests."""
    return os.environ.get("ALPHA_VANTAGE_API_KEY", "demo")
