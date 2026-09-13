"""StockTwits fetch: transport-error resilience (#1024) and crypto symbol
mapping (#1113).

StockTwits lists crypto under ``<BASE>.X`` (Yahoo's ``BTC-USD`` 404s), and any
transport error must degrade to a placeholder rather than raise.
"""

from __future__ import annotations

import http.client
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from tradingagents.dataflows import stocktwits


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
            # Indian listings: StockTwits indexes the bare cashtag (#1345)
            ("RELIANCE.NS", "RELIANCE"),
            ("HDFCBANK.BO", "HDFCBANK"),
            ("infy.ns", "INFY"),      # case-insensitive, like every other row
            ("TCS.NSE", "TCS"),
            ("SBIN.BSE", "SBIN"),
            # Dotted symbols StockTwits DOES index: a generic "strip after the
            # dot" would send these to another security's stream.
            ("BRK.B", "BRK.B"),
            ("BF.B", "BF.B"),
            # Other exchange suffixes are deliberately left alone: `$SHEL` on
            # StockTwits is the US ADR, a different instrument from `SHEL.L`.
            ("SHEL.L", "SHEL.L"),
            ("7203.T", "7203.T"),
            # A symbol that is ONLY a suffix must not become empty and build
            # `streams/symbol/.json`.
            (".NS", ".NS"),
        ],
    )
    def test_symbol_mapping(self, ticker, expected):
        assert stocktwits._stocktwits_symbol(ticker) == expected

    def test_indian_listing_requests_the_bare_cashtag_endpoint(self):
        """End to end: the suffix is gone from the URL the fetcher opens, which
        is the only place the mapping has an effect (#1345)."""
        seen = {}

        def _capture(req, timeout=None):
            seen["url"] = req.full_url
            raise HTTPError(req.full_url, 404, "Not Found", {}, None)

        with patch("tradingagents.dataflows.stocktwits.urlopen", _capture):
            stocktwits.fetch_stocktwits_messages("RELIANCE.NS")

        assert "/streams/symbol/RELIANCE.json" in seen["url"], seen["url"]
        assert ".NS" not in seen["url"], seen["url"]

    def test_crypto_pair_requests_dot_x_endpoint(self):
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            raise TimeoutError("stop after capturing the URL")

        with patch.object(stocktwits, "urlopen", side_effect=fake_urlopen):
            stocktwits.fetch_stocktwits_messages("BTC-USD")
        assert "/symbol/BTC.X.json" in seen["url"]
