from unittest.mock import patch

import pytest
import requests

from tradingagents.dataflows.alpha_vantage_common import (
    DEFAULT_ALPHA_VANTAGE_TIMEOUT,
    AlphaVantageTemporaryError,
    _make_api_request,
)


def test_alpha_vantage_request_uses_timeout(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "key")
    captured = {}

    class Response:
        text = "timestamp,open\n2026-01-01,1\n"

        def raise_for_status(self):
            pass

    def fake_get(url, params, timeout):
        captured["timeout"] = timeout
        return Response()

    with patch("tradingagents.dataflows.alpha_vantage_common.requests.get", side_effect=fake_get):
        _make_api_request("TIME_SERIES_DAILY_ADJUSTED", {"symbol": "AAPL"})

    assert captured["timeout"] == DEFAULT_ALPHA_VANTAGE_TIMEOUT


def test_alpha_vantage_timeout_raises_temporary_error(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "key")
    with patch(
        "tradingagents.dataflows.alpha_vantage_common.requests.get",
        side_effect=requests.Timeout,
    ):
        with pytest.raises(AlphaVantageTemporaryError):
            _make_api_request("TIME_SERIES_DAILY_ADJUSTED", {"symbol": "AAPL"})
