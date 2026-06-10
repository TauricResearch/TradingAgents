"""Tests for Alpha Vantage request hardening.

Covers:
  - #990: HTTP requests must pass a bounded timeout so a stalled network path
    cannot block analysis indefinitely.
  - #991: an invalid/missing API key must not be mislabeled as a rate-limit
    error, while genuine rate-limit messages (which can also mention the API
    key) must stay rate-limit errors.
"""

import json
import unittest
from unittest import mock

import pytest

from tradingagents.dataflows import alpha_vantage_common as av
from tradingagents.dataflows.alpha_vantage_common import (
    AlphaVantageNotConfiguredError,
    AlphaVantageRateLimitError,
)


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


@pytest.mark.unit
class TestAlphaVantageRequest(unittest.TestCase):
    def test_request_passes_timeout(self):
        captured = {}

        def fake_get(url, params=None, timeout=None):
            captured["timeout"] = timeout
            return _FakeResponse("timestamp,open\n2026-01-01,1.0\n")

        with mock.patch.object(av, "get_api_key", return_value="demo"), \
                mock.patch.object(av.requests, "get", side_effect=fake_get):
            av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

        self.assertEqual(captured["timeout"], av.REQUEST_TIMEOUT)

    def test_api_key_message_raises_not_configured(self):
        body = json.dumps(
            {"Information": "Invalid API key. Please claim your free API key."}
        )
        with mock.patch.object(av, "get_api_key", return_value="demo"), \
                mock.patch.object(av.requests, "get", return_value=_FakeResponse(body)):
            with self.assertRaises(AlphaVantageNotConfiguredError):
                av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    def test_rate_limit_message_stays_rate_limit_even_when_mentioning_api_key(self):
        # Regression guard: AV throttling messages also mention the API key.
        body = json.dumps(
            {
                "Information": (
                    "We have detected your API key as DEMO and our standard "
                    "API rate limit is 25 requests per day."
                )
            }
        )
        with mock.patch.object(av, "get_api_key", return_value="demo"), \
                mock.patch.object(av.requests, "get", return_value=_FakeResponse(body)):
            with self.assertRaises(AlphaVantageRateLimitError):
                av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    def test_csv_response_passes_through(self):
        csv_text = "timestamp,open,close\n2026-01-02,1.0,1.1\n"
        with mock.patch.object(av, "get_api_key", return_value="demo"), \
                mock.patch.object(av.requests, "get", return_value=_FakeResponse(csv_text)):
            result = av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
        self.assertEqual(result, csv_text)

    def test_unexpected_json_shape_passes_through(self):
        body = json.dumps(["unexpected", "payload"])
        with mock.patch.object(av, "get_api_key", return_value="demo"), \
                mock.patch.object(av.requests, "get", return_value=_FakeResponse(body)):
            result = av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
        self.assertEqual(result, body)

    def test_non_string_information_passes_through(self):
        body = json.dumps({"Information": {"message": "Invalid API key"}})
        with mock.patch.object(av, "get_api_key", return_value="demo"), \
                mock.patch.object(av.requests, "get", return_value=_FakeResponse(body)):
            result = av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
        self.assertEqual(result, body)


if __name__ == "__main__":
    unittest.main()
