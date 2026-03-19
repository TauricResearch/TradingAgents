"""Unit tests for Alpha Vantage exception hierarchy and error-handling logic."""

import requests as _requests
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


class TestMakeApiRequestErrorHandling:
    """Unit tests for _make_api_request error-handling — all HTTP calls are mocked."""

    def test_timeout_raises_timeout_error(self):
        """When requests.get raises Timeout, _make_api_request should raise ThirdPartyTimeoutError."""
        with patch(
            "tradingagents.dataflows.alpha_vantage_common.requests.get",
            side_effect=_requests.exceptions.Timeout("simulated timeout"),
        ):
            with pytest.raises(ThirdPartyTimeoutError):
                _make_api_request("TIME_SERIES_DAILY", {"symbol": "IBM"})

    def test_connection_error_raises_third_party_error(self):
        """When requests.get raises ConnectionError, _make_api_request raises ThirdPartyError."""
        with patch(
            "tradingagents.dataflows.alpha_vantage_common.requests.get",
            side_effect=_requests.exceptions.ConnectionError("simulated connection error"),
        ):
            with pytest.raises(ThirdPartyError):
                _make_api_request("TIME_SERIES_DAILY", {"symbol": "IBM"})
