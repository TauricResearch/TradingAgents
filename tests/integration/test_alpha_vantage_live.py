"""Live integration tests for the Alpha Vantage data layer.

These tests make real HTTP requests to the Alpha Vantage API.
Excluded from the default pytest run.

Run with:
    pytest tests/integration/ -v
    pytest tests/integration/test_alpha_vantage_live.py -v -m integration
"""

import os
import pytest
from unittest.mock import patch

from tradingagents.dataflows.alpha_vantage_common import (
    AlphaVantageError,
    _make_api_request,
    ThirdPartyTimeoutError,
)


@pytest.mark.integration
class TestMakeApiRequestErrors:
    """Test _make_api_request error handling with real HTTP calls."""

    def test_invalid_api_key(self):
        """An invalid API key should raise AlphaVantageError or return demo data."""
        with patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "INVALID_KEY_12345"}):
            try:
                result = _make_api_request("TIME_SERIES_DAILY", {"symbol": "IBM"})
                # AV may silently fall back to demo-key behaviour
                assert result is not None
            except AlphaVantageError:
                pass  # Expected — any AV error is acceptable here

    def test_timeout_raises_timeout_error(self):
        """A very short timeout should raise ThirdPartyTimeoutError."""
        with pytest.raises(ThirdPartyTimeoutError):
            _make_api_request(
                "TIME_SERIES_DAILY",
                {"symbol": "IBM"},
                timeout=0.001,
            )

    def test_valid_request_succeeds(self, av_api_key):
        """A valid request with a real key should return non-empty data."""
        result = _make_api_request("GLOBAL_QUOTE", {"symbol": "IBM"})
        assert result is not None
        assert len(result) > 0
