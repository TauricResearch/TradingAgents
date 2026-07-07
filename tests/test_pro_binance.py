"""Binance adapters against canned payloads (no network)."""

import pytest

from tests.pro_fakes import FakeTransport
from tradingagents.contracts import Timeframe
from tradingagents.dataflows.errors import NoMarketDataError, VendorRateLimitError
from tradingagents.pro.ingestion.binance import BinanceDerivativesFeed, BinanceSpotFeed

KLINES = [
    # openTime, open, high, low, close, volume, closeTime, ...
    [1750000000000, "60000.0", "60500.0", "59800.0", "60200.0", "123.45", 1750003599999],
    [1750003600000, "60200.0", "60900.0", "60100.0", "60800.0", "98.70", 1750007199999],
]

ROUTES = {
    "/api/v3/klines": KLINES,
    "/api/v3/ticker/bookTicker": {"symbol": "BTCUSDT", "bidPrice": "60790.0", "askPrice": "60791.0"},
    "/api/v3/ticker/price": {"symbol": "BTCUSDT", "price": "60790.5"},
    "/api/v3/depth": {
        "bids": [["60790.0", "3.0"], ["60789.0", "1.0"]],
        "asks": [["60791.0", "1.0"]],
    },
    "/fapi/v1/premiumIndex": {
        "symbol": "BTCUSDT",
        "markPrice": "60795.00",
        "lastFundingRate": "0.00010000",
        "time": 1750007200000,
    },
    "/fapi/v1/openInterest": {
        "symbol": "BTCUSDT",
        "openInterest": "85000.123",
        "time": 1750007200000,
    },
}


def make_spot(routes=None) -> BinanceSpotFeed:
    return BinanceSpotFeed(transport=FakeTransport(routes or ROUTES))


def test_klines_become_validated_bars():
    bars = make_spot().get_bars("BTCUSDT", Timeframe.H1, limit=2)
    assert len(bars) == 2
    assert bars[0].open == 60000.0 and bars[0].close == 60200.0
    assert bars[0].start.tzinfo is not None
    assert bars[1].timeframe is Timeframe.H1


def test_interval_param_matches_contract_timeframe_value():
    transport = FakeTransport(ROUTES)
    BinanceSpotFeed(transport=transport).get_bars("BTCUSDT", Timeframe.H4)
    url, params = transport.calls[0]
    assert params["interval"] == "4h"


def test_empty_klines_raise_no_market_data():
    with pytest.raises(NoMarketDataError):
        make_spot({**ROUTES, "/api/v3/klines": []}).get_bars("BTCUSDT", Timeframe.H1)


def test_quote_combines_book_and_last():
    quote = make_spot().get_quote("BTCUSDT")
    assert quote.bid == 60790.0 and quote.ask == 60791.0 and quote.last == 60790.5
    assert quote.ts.tzinfo is not None


def test_orderbook_imbalance_reading():
    reading = make_spot().get_orderbook_imbalance("BTCUSDT", depth=100)
    # bids 4.0, asks 1.0 -> 3/5 = 0.6
    assert reading.value == pytest.approx(0.6)
    assert reading.name == "ORDERBOOK_IMBALANCE_100"
    assert reading.source == "binance_spot"


def test_derivatives_metrics():
    feed = BinanceDerivativesFeed(transport=FakeTransport(ROUTES))
    readings = {r.name: r for r in feed.get_metrics()}
    assert readings["FUNDING_RATE"].value == pytest.approx(0.0001)
    assert readings["MARK_PRICE"].value == pytest.approx(60795.0)
    assert readings["OPEN_INTEREST"].value == pytest.approx(85000.123)
    assert readings["OPEN_INTEREST"].unit == "BTC"


def test_http_429_maps_to_rate_limit_error():
    class Throttled:
        def get_json(self, url, params=None):
            raise VendorRateLimitError("HTTP 429")

    with pytest.raises(VendorRateLimitError):
        BinanceSpotFeed(transport=Throttled()).get_bars("BTCUSDT", Timeframe.H1)
