"""StockTwits fetch: transport-error resilience (#1024) and crypto symbol
mapping (#1113).

StockTwits lists crypto under ``<BASE>.X`` (Yahoo's ``BTC-USD`` 404s), and any
transport error must degrade to a placeholder rather than raise.
"""

from __future__ import annotations

import http.client
import json
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from tradingagents.dataflows.vendors import stocktwits


def _raise(exc):
    class _Resp:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

        def read(self_inner):
            raise exc
    return _Resp()


@pytest.mark.unit
class TestStockTwitsResilience:
    @pytest.mark.parametrize(
        "exc",
        [
            http.client.IncompleteRead(b""),
            HTTPError("url", 503, "down", {}, None),
            TimeoutError("slow"),
        ],
    )
    def test_transport_errors_return_placeholder(self, exc):
        with patch.object(stocktwits, "urlopen", return_value=_raise(exc)):
            out = stocktwits.fetch_stocktwits_messages("NVDA")
        assert "unavailable" in out.lower()
        assert out.startswith("<stocktwits unavailable")


@pytest.mark.unit
class TestStockTwitsCryptoSymbols:
    @pytest.mark.parametrize(
        ("ticker", "expected"),
        [
            ("BTC-USD", "BTC.X"),
            ("eth-usd", "ETH.X"),
            ("SOL-USD", "SOL.X"),
            ("BTCUSD", "BTC.X"),      # undashed broker form
            ("BTC-USDT", "BTC.X"),    # stablecoin quote
            ("AMD", "AMD"),
            ("BRK-B", "BRK-B"),       # dashed class share: untouched
            ("GOLD", "GOLD"),         # real equity (aliases elsewhere): untouched here
            ("XYZ-USD", "XYZ-USD"),   # unknown base: not treated as crypto
        ],
    )
    def test_symbol_mapping(self, ticker, expected):
        assert stocktwits._stocktwits_symbol(ticker) == expected

    def test_crypto_pair_requests_dot_x_endpoint(self):
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            raise TimeoutError("stop after capturing the URL")

        with patch.object(stocktwits, "urlopen", side_effect=fake_urlopen):
            stocktwits.fetch_stocktwits_messages("BTC-USD")
        assert "/symbol/BTC.X.json" in seen["url"]


def _stream(*bodies):
    payload = {"messages": [
        {"body": b, "created_at": "2026-01-09T15:00:00Z", "user": {"username": "u"},
         "entities": {"sentiment": {"basic": "Bullish"}}}
        for b in bodies
    ]}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode()
    return _Resp()


def _drop_spam(texts):
    return [not t.startswith("SPAM") for t in texts], "Screened: note"


@pytest.mark.unit
class TestStockTwitsScreening:
    def test_screened_out_messages_leave_the_block_and_its_counts(self):
        with patch.object(stocktwits, "urlopen", return_value=_stream("SPAM", "long NVDA")):
            out = stocktwits.fetch_stocktwits_messages("NVDA", screen=_drop_spam)
        assert out.startswith("Screened: note")
        assert "long NVDA" in out and "SPAM" not in out
        assert "Total: 1 most-recent" in out

    def test_all_screened_out_is_not_called_empty(self):
        with patch.object(stocktwits, "urlopen", return_value=_stream("SPAM")):
            out = stocktwits.fetch_stocktwits_messages("NVDA", screen=_drop_spam)
        assert "none of the 1 StockTwits messages is about $NVDA" in out


@pytest.mark.unit
def test_html_entities_in_message_bodies_are_decoded():
    with patch.object(stocktwits, "urlopen", return_value=_stream("S&amp;P wasn&#39;t up")):
        out = stocktwits.fetch_stocktwits_messages("NVDA")
    assert "S&P wasn't up" in out
