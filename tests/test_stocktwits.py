"""Unit tests for tradingagents/dataflows/stocktwits.py."""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages

pytestmark = pytest.mark.unit

_ST_SAMPLE = {
    "messages": [
        {
            "created_at": "2026-06-15T10:00:00Z",
            "user": {"username": "trader1"},
            "entities": {"sentiment": {"basic": "Bullish"}},
            "body": "This stock is going to the moon!",
        },
        {
            "created_at": "2026-06-15T11:00:00Z",
            "user": {"username": "bear2"},
            "entities": {"sentiment": {"basic": "Bearish"}},
            "body": "Selling all shares.",
        },
    ]
}

_LONG_BODY = (
    "This is an extremely long message body that is well over two hundred "
    "and eighty characters in length and therefore needs to be truncated "
    "by the fetch_stocktwits_messages function so that each message fits "
    "within a reasonable display size and does not blow up the context "
    "window for the LLM consuming this data. " * 3
)


class StocktwitsFetchTests(unittest.TestCase):
    """Lines 47-49 (error handling), 53 (empty messages), 66-68 (date parse fail-open)."""

    def _mock_urlopen(self, data: bytes = None, side_effect: Exception = None):
        if side_effect:
            return patch("tradingagents.dataflows.stocktwits.urlopen", side_effect=side_effect)
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = data or b'{"messages": []}'
        return patch("tradingagents.dataflows.stocktwits.urlopen", return_value=mock_resp)

    def test_http_error_returns_unavailable(self):
        from urllib.error import HTTPError

        with self._mock_urlopen(side_effect=HTTPError("url", 404, "Not Found", {}, None)):
            result = fetch_stocktwits_messages("AAPL")
        self.assertIn("stocktwits unavailable", result)
        self.assertIn("HTTPError", result)

    def test_url_error_returns_unavailable(self):
        from urllib.error import URLError

        with self._mock_urlopen(side_effect=URLError("host unreachable")):
            result = fetch_stocktwits_messages("AAPL")
        self.assertIn("stocktwits unavailable", result)
        self.assertIn("URLError", result)

    def test_json_decode_error_returns_unavailable(self):
        with self._mock_urlopen(data=b"not json"):
            result = fetch_stocktwits_messages("AAPL")
        self.assertIn("stocktwits unavailable", result)
        self.assertIn("JSONDecodeError", result)

    def test_timeout_error_returns_unavailable(self):
        with self._mock_urlopen(side_effect=TimeoutError("timed out")):
            result = fetch_stocktwits_messages("AAPL")
        self.assertIn("stocktwits unavailable", result)
        self.assertIn("TimeoutError", result)

    def test_empty_messages_returns_no_messages(self):
        with self._mock_urlopen(data=b'{"messages": []}'):
            result = fetch_stocktwits_messages("AAPL")
        self.assertIn("no StockTwits messages found", result)
        self.assertIn("AAPL", result)

    def test_date_parse_fail_open(self):
        messages = [
            {"created_at": "invalid-date!!", "body": "Great stock!", "user": {"username": "trader1"}},
            {"created_at": "2026-06-18T10:30:00Z", "body": "To the moon!", "user": {"username": "trader2"}},
        ]
        payload = json.dumps({"messages": messages}).encode("utf-8")

        with self._mock_urlopen(data=payload):
            result = fetch_stocktwits_messages("AAPL", days_back=7)
        self.assertIn("Great stock!", result)
        self.assertIn("To the moon!", result)

    def test_success_path_returns_formatted_messages(self):
        messages = [
            {"created_at": "2026-06-18T10:30:00Z", "body": "Bullish on AAPL", "user": {"username": "bull1"},
             "entities": {"sentiment": {"basic": "Bullish"}}},
            {"created_at": "2026-06-17T09:00:00Z", "body": "Too expensive", "user": {"username": "bear1"},
             "entities": {"sentiment": {"basic": "Bearish"}}},
        ]
        payload = json.dumps({"messages": messages}).encode("utf-8")

        with self._mock_urlopen(data=payload):
            result = fetch_stocktwits_messages("AAPL", days_back=30)
        self.assertIn("Bullish", result)
        self.assertIn("Bearish", result)
        self.assertIn("AAPL", result)


class TestStocktwitsEdgeCases(unittest.TestCase):
    """Body truncation, sentiment edge, days_back."""

    def test_body_truncation(self):
        data = dict(_ST_SAMPLE)
        data["messages"][0]["body"] = _LONG_BODY

        with patch("tradingagents.dataflows.stocktwits.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.read.return_value = json.dumps(data).encode("utf-8")
            mock_urlopen.return_value = mock_resp

            result = fetch_stocktwits_messages("AAPL", limit=5)
        self.assertIn("\u2026", result)

    def test_no_sentiment_key(self):
        data = {
            "messages": [
                {
                    "created_at": "2026-06-15T10:00:00Z",
                    "user": {"username": "trader1"},
                    "entities": {},
                    "body": "No sentiment here.",
                },
            ]
        }

        with patch("tradingagents.dataflows.stocktwits.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.read.return_value = json.dumps(data).encode("utf-8")
            mock_urlopen.return_value = mock_resp

            result = fetch_stocktwits_messages("AAPL", limit=5)
        self.assertIn("no-label", result)

    def test_no_entities_key(self):
        data = dict(_ST_SAMPLE)
        data["messages"][0].pop("entities", None)

        with patch("tradingagents.dataflows.stocktwits.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.read.return_value = json.dumps(data).encode("utf-8")
            mock_urlopen.return_value = mock_resp

            result = fetch_stocktwits_messages("AAPL", limit=5)
        self.assertIn("no-label", result)

    def test_days_back_zero_includes_all(self):
        with patch("tradingagents.dataflows.stocktwits.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.read.return_value = json.dumps(_ST_SAMPLE).encode("utf-8")
            mock_urlopen.return_value = mock_resp

            result = fetch_stocktwits_messages("AAPL", limit=5, days_back=0)
        self.assertIn("Bullish", result)

    def test_missing_user_object(self):
        data = dict(_ST_SAMPLE)
        data["messages"][0]["user"] = None

        with patch("tradingagents.dataflows.stocktwits.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.read.return_value = json.dumps(data).encode("utf-8")
            mock_urlopen.return_value = mock_resp

            result = fetch_stocktwits_messages("AAPL", limit=5)
        self.assertIn("Bullish", result)
