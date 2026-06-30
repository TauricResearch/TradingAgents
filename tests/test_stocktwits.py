"""Tests for the StockTwits message fetcher."""

import json
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages


def _make_message(body, sentiment=None, username="user1", created_at="2026-01-15T10:00:00Z"):
    msg = {
        "body": body,
        "created_at": created_at,
        "user": {"username": username},
        "entities": {},
    }
    if sentiment:
        msg["entities"]["sentiment"] = {"basic": sentiment}
    return msg


def _mock_urlopen(messages):
    """Patch urlopen to return a mock response with the given messages."""
    data = json.dumps({"messages": messages}).encode()
    resp = MagicMock()
    resp.read.return_value = data
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@pytest.mark.unit
class TestFetchStocktwitsMessages:
    @patch("tradingagents.dataflows.stocktwits.urlopen")
    def test_basic_bullish_messages(self, mock_urlopen_fn):
        messages = [
            _make_message("NVDA to the moon!", sentiment="Bullish"),
            _make_message("Strong earnings!", sentiment="Bullish"),
        ]
        mock_urlopen_fn.return_value = _mock_urlopen(messages)

        result = fetch_stocktwits_messages("NVDA")
        assert "Bullish: 2 (100%)" in result
        assert "NVDA to the moon!" in result
        assert "Strong earnings!" in result

    @patch("tradingagents.dataflows.stocktwits.urlopen")
    def test_mixed_sentiment(self, mock_urlopen_fn):
        messages = [
            _make_message("Going up!", sentiment="Bullish"),
            _make_message("Going down!", sentiment="Bearish"),
            _make_message("Who knows?"),
        ]
        mock_urlopen_fn.return_value = _mock_urlopen(messages)

        result = fetch_stocktwits_messages("AAPL")
        assert "Bullish: 1" in result
        assert "Bearish: 1" in result
        assert "Unlabeled: 1" in result
        assert "Total: 3" in result

    @patch("tradingagents.dataflows.stocktwits.urlopen")
    def test_empty_messages(self, mock_urlopen_fn):
        mock_urlopen_fn.return_value = _mock_urlopen([])

        result = fetch_stocktwits_messages("XYZ")
        assert "no StockTwits messages found" in result

    @patch("tradingagents.dataflows.stocktwits.urlopen")
    def test_http_error_returns_unavailable(self, mock_urlopen_fn):
        from urllib.error import HTTPError
        mock_urlopen_fn.side_effect = HTTPError(
            url="http://test", code=429, msg="Rate limited", hdrs={}, fp=None
        )

        result = fetch_stocktwits_messages("NVDA")
        assert "unavailable" in result
        assert "HTTPError" in result

    @patch("tradingagents.dataflows.stocktwits.urlopen")
    def test_url_error_returns_unavailable(self, mock_urlopen_fn):
        from urllib.error import URLError
        mock_urlopen_fn.side_effect = URLError("DNS failure")

        result = fetch_stocktwits_messages("NVDA")
        assert "unavailable" in result

    @patch("tradingagents.dataflows.stocktwits.urlopen")
    def test_timeout_returns_unavailable(self, mock_urlopen_fn):
        mock_urlopen_fn.side_effect = TimeoutError("timed out")

        result = fetch_stocktwits_messages("NVDA")
        assert "unavailable" in result

    @patch("tradingagents.dataflows.stocktwits.urlopen")
    def test_malformed_json_returns_unavailable(self, mock_urlopen_fn):
        resp = MagicMock()
        resp.read.return_value = b"not json"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen_fn.return_value = resp

        result = fetch_stocktwits_messages("NVDA")
        assert "unavailable" in result

    @patch("tradingagents.dataflows.stocktwits.urlopen")
    def test_long_body_truncated(self, mock_urlopen_fn):
        long_body = "A" * 500
        messages = [_make_message(long_body, sentiment="Bullish")]
        mock_urlopen_fn.return_value = _mock_urlopen(messages)

        result = fetch_stocktwits_messages("NVDA")
        assert len(long_body) > 280
        assert "A" * 280 in result

    @patch("tradingagents.dataflows.stocktwits.urlopen")
    def test_limit_parameter(self, mock_urlopen_fn):
        messages = [_make_message(f"Msg {i}", sentiment="Bullish") for i in range(10)]
        mock_urlopen_fn.return_value = _mock_urlopen(messages)

        result = fetch_stocktwits_messages("NVDA", limit=3)
        assert "Total: 3" in result

    @patch("tradingagents.dataflows.stocktwits.urlopen")
    def test_ticker_uppercased_in_url(self, mock_urlopen_fn):
        mock_urlopen_fn.return_value = _mock_urlopen([])
        fetch_stocktwits_messages("nvda")
        call_args = mock_urlopen_fn.call_args
        request = call_args[0][0]
        assert "NVDA" in request.full_url

    @patch("tradingagents.dataflows.stocktwits.urlopen")
    def test_unexpected_response_shape(self, mock_urlopen_fn):
        resp = MagicMock()
        resp.read.return_value = json.dumps({"unexpected": True}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen_fn.return_value = resp

        result = fetch_stocktwits_messages("NVDA")
        assert "no StockTwits messages found" in result
