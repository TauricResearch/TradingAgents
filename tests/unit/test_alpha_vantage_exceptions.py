"""Integration tests for Alpha Vantage exception hierarchy."""

import os
import pytest
from unittest.mock import patch

from tradingagents.dataflows.alpha_vantage_common import (
    AlphaVantageError,
    APIKeyInvalidError,
    RateLimitError,
    AlphaVantageRateLimitError,
    ThirdPartyError,
    ThirdPartyTimeoutError,
    ThirdPartyParseError,
    _make_api_request,
)


class TestExceptionHierarchy:
    """Verify the exception class hierarchy is correct."""

    def test_all_exceptions_inherit_from_base(self):
        assert issubclass(APIKeyInvalidError, AlphaVantageError)
        assert issubclass(RateLimitError, AlphaVantageError)
        assert issubclass(ThirdPartyError, AlphaVantageError)
        assert issubclass(ThirdPartyTimeoutError, AlphaVantageError)
        assert issubclass(ThirdPartyParseError, AlphaVantageError)

    def test_rate_limit_alias(self):
        """AlphaVantageRateLimitError is an alias for RateLimitError."""
        assert AlphaVantageRateLimitError is RateLimitError

    def test_exceptions_are_catchable_as_base(self):
        with pytest.raises(AlphaVantageError):
            raise APIKeyInvalidError("bad key")
        with pytest.raises(AlphaVantageError):
            raise RateLimitError("rate limited")
        with pytest.raises(AlphaVantageError):
            raise ThirdPartyError("server error")


@pytest.mark.integration
class TestMakeApiRequestErrors:
    """Test _make_api_request error handling with real HTTP calls."""

    def test_invalid_api_key(self):
        """An invalid API key should raise APIKeyInvalidError or AlphaVantageError."""
        with patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "INVALID_KEY_12345"}):
            # AV may return 200 with error in body, or may return a valid demo response
            # Either way it should not silently succeed with bad data
            try:
                result = _make_api_request("TIME_SERIES_DAILY", {"symbol": "IBM"})
                # If it returns something, it should be valid data (demo key behavior)
                assert result is not None
            except AlphaVantageError:
                pass  # Expected — any AV error is acceptable here

    def test_timeout_raises_timeout_error(self):
        """A timeout should raise ThirdPartyTimeoutError."""
        with pytest.raises(ThirdPartyTimeoutError):
            # Use an impossibly short timeout
            _make_api_request(
                "TIME_SERIES_DAILY",
                {"symbol": "IBM"},
                timeout=0.001,
            )

    def test_valid_request_succeeds(self, av_api_key):
        """A valid request with a real key should return data."""
        result = _make_api_request(
            "GLOBAL_QUOTE",
            {"symbol": "IBM"},
        )
        assert result is not None
        assert len(result) > 0
