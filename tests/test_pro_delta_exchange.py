"""Delta Exchange adapter: mapping, ordering, probe gating (offline fakes)."""

import pytest

from tradingagents.contracts import Timeframe
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.pro.ingestion.delta_exchange import RESOLUTIONS, DeltaExchangeFeed

TICKER_PAYLOAD = {
    "success": True,
    "result": {
        "quotes": {"best_ask": "62838.5", "best_bid": "62837.5"},
        "mark_price": "62835.17308624",
        "funding_rate": "0.010000000000000002",
        "oi_value_usd": "49966693.1672",
        "open": 62006.0,
    },
}


class FakeTransport:
    def __init__(self, candles=None, ticker=TICKER_PAYLOAD):
        self.requests = []
        self.candles = candles
        self.ticker = ticker

    def get_json(self, url, params=None):
        self.requests.append((url, params))
        if "history/candles" in url:
            return self.candles
        return self.ticker


def candle_payload(n=5, descending=True):
    rows = [
        {"time": 1783580400 + i * 3600, "open": 100 + i, "high": 105 + i,
         "low": 95 + i, "close": 101 + i, "volume": 1000 + i}
        for i in range(n)
    ]
    if descending:
        rows.reverse()  # Delta returns newest-first
    return {"success": True, "result": rows}


class TestDeltaBars:
    def test_bars_sorted_ascending_and_validated(self):
        transport = FakeTransport(candles=candle_payload())
        feed = DeltaExchangeFeed(transport=transport)
        bars = feed.get_bars("BTCUSD", Timeframe.H1, limit=5)
        assert len(bars) == 5
        assert bars[0].start < bars[-1].start  # re-sorted despite newest-first
        assert bars[-1].close == 105.0
        url, params = transport.requests[0]
        assert "history/candles" in url
        assert params["symbol"] == "BTCUSD" and params["resolution"] == "1h"
        assert params["start"] < params["end"]

    def test_resolution_map_covers_all_timeframes(self):
        assert set(RESOLUTIONS) == set(Timeframe)

    def test_empty_result_raises(self):
        feed = DeltaExchangeFeed(
            transport=FakeTransport(candles={"success": True, "result": []})
        )
        with pytest.raises(NoMarketDataError):
            feed.get_bars("BTCUSD", Timeframe.H1)

    def test_base_url_override(self, monkeypatch):
        monkeypatch.setenv("DELTA_BASE_URL", "https://api.delta.exchange/")
        transport = FakeTransport(candles=candle_payload())
        feed = DeltaExchangeFeed(transport=transport)
        feed.get_bars("PAXGUSD", Timeframe.D1, limit=2)
        assert transport.requests[0][0].startswith(
            "https://api.delta.exchange/v2/"
        )


class TestDeltaQuoteAndMetrics:
    def test_quote_from_ticker(self):
        feed = DeltaExchangeFeed(transport=FakeTransport())
        quote = feed.get_quote("BTCUSD")
        assert quote.bid == 62837.5 and quote.ask == 62838.5
        assert quote.last == pytest.approx(62835.17308624)

    def test_quote_missing_book_raises(self):
        feed = DeltaExchangeFeed(transport=FakeTransport(
            ticker={"success": True, "result": {"quotes": {}, "mark_price": "1"}}
        ))
        with pytest.raises(NoMarketDataError):
            feed.get_quote("BTCUSD")

    def test_metrics_labeled_with_venue_units(self):
        feed = DeltaExchangeFeed(transport=FakeTransport())
        metrics = {m.name: m for m in feed.get_metrics("BTCUSD")}
        assert metrics["FUNDING_RATE"].unit == "pct_8h"
        assert metrics["FUNDING_RATE"].value == pytest.approx(0.01)
        assert metrics["OPEN_INTEREST"].value == pytest.approx(49966693.1672)
        assert all(m.source == "delta_exchange" for m in metrics.values())


class TestProbe:
    def test_probe_false_on_error(self, monkeypatch):
        monkeypatch.setattr(
            DeltaExchangeFeed, "get_bars",
            lambda self, *a, **k: (_ for _ in ()).throw(ConnectionError()),
        )
        assert DeltaExchangeFeed.probe(timeout=0.1) is False

    def test_kill_switch_short_circuits_without_network(self, monkeypatch):
        calls = []
        monkeypatch.setenv("PRO_DISABLE_LIVE_VENDORS", "1")
        monkeypatch.setattr(
            DeltaExchangeFeed, "get_bars",
            lambda self, *a, **k: calls.append(1),
        )
        assert DeltaExchangeFeed.probe() is False
        assert calls == []
