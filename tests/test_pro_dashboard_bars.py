"""Market data service, bars/indicator endpoints, OANDA feed, tick poller."""

import threading
from datetime import timedelta

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from tests.pro_fakes import BASE_TS, make_bars  # noqa: E402
from tradingagents.contracts import OHLCVBar, Timeframe  # noqa: E402
from tradingagents.dataflows.errors import (  # noqa: E402
    NoMarketDataError,
    VendorRateLimitError,
)
from tradingagents.pro.dashboard.app import DashboardState, create_app  # noqa: E402
from tradingagents.pro.dashboard.events import EventBroadcaster  # noqa: E402
from tradingagents.pro.dashboard.marketdata import (  # noqa: E402
    MarketDataService,
    SymbolSpec,
    UnknownSymbolError,
    UnsupportedTimeframeError,
    bars_view,
    indicator_series_view,
)
from tradingagents.pro.dashboard.ticker import GoldTickPoller  # noqa: E402
from tradingagents.pro.ingestion.oanda_gold import (  # noqa: E402
    OandaGoldFeed,
    OandaNotConfiguredError,
)


class CountingFeed:
    name = "counting"

    def __init__(self, n=250, timeframe=Timeframe.D1):
        self.calls = 0
        self.n = n
        self.timeframe = timeframe

    def get_bars(self, symbol, timeframe, *, limit=250, end=None):
        self.calls += 1
        return make_bars(self.n, timeframe=timeframe)


def make_registry(feed, timeframes=(Timeframe.D1, Timeframe.H1)):
    return {
        "XAUUSD": SymbolSpec(
            symbol="XAUUSD", vendor_symbol="GC=F", source="counting",
            timeframes=timeframes, live=False, feed_factory=lambda: feed,
        )
    }


class TestMarketDataService:
    def test_bars_shape_for_lightweight_charts(self):
        feed = CountingFeed()
        service = MarketDataService(make_registry(feed))
        rows = bars_view(service.get_bars("XAUUSD", Timeframe.D1, limit=10))
        assert len(rows) == 10
        first = rows[0]
        assert set(first) == {"time", "open", "high", "low", "close", "volume"}
        assert isinstance(first["time"], int)
        times = [r["time"] for r in rows]
        assert times == sorted(times)

    def test_ttl_cache_and_expiry(self):
        clock = {"t": 0.0}
        feed = CountingFeed()
        service = MarketDataService(make_registry(feed), now=lambda: clock["t"])
        service.get_bars("XAUUSD", Timeframe.D1, 10)
        service.get_bars("XAUUSD", Timeframe.D1, 50)  # same key, cached
        assert feed.calls == 1
        clock["t"] = 400.0  # past the 300s daily-cap TTL
        service.get_bars("XAUUSD", Timeframe.D1, 10)
        assert feed.calls == 2

    def test_single_flight_under_concurrency(self):
        feed = CountingFeed()
        slow = threading.Event()
        original = feed.get_bars

        def slow_get(*args, **kwargs):
            slow.wait(0.2)
            return original(*args, **kwargs)

        feed.get_bars = slow_get
        service = MarketDataService(make_registry(feed))
        threads = [
            threading.Thread(
                target=service.get_bars, args=("XAUUSD", Timeframe.D1, 10)
            )
            for _ in range(8)
        ]
        slow.set()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert feed.calls == 1

    def test_unknown_symbol_and_unsupported_timeframe(self):
        service = MarketDataService(make_registry(CountingFeed()))
        with pytest.raises(UnknownSymbolError):
            service.get_bars("DOGE", Timeframe.D1)
        with pytest.raises(UnsupportedTimeframeError, match="1m"):
            service.get_bars("XAUUSD", Timeframe.M1)

    def test_limit_clamped(self):
        feed = CountingFeed(n=250)
        service = MarketDataService(make_registry(feed))
        assert len(service.get_bars("XAUUSD", Timeframe.D1, 99999)) == 250


class TestIndicatorSeries:
    def test_series_align_with_latest_point_values(self):
        from tradingagents.pro.ingestion.indicators import compute_indicators

        bars = make_bars(60)
        view = indicator_series_view(bars, ("RSI_14", "MACD"))
        latest = {r.name: r.value for r in compute_indicators(bars, ("RSI_14", "MACD"))}
        rsi_points = view["RSI_14"]["series"]["value"]
        # warm-up dropped: first point is at bar index 14 (min_bars 15)
        assert len(rsi_points) == 60 - 14
        assert rsi_points[-1]["value"] == pytest.approx(latest["RSI_14"]["value"])
        assert rsi_points[-1]["time"] == int(bars[-1].start.timestamp())
        assert view["MACD"]["series"]["histogram"][-1]["value"] == pytest.approx(
            latest["MACD"]["histogram"]
        )

    def test_unknown_indicator_raises(self):
        with pytest.raises(ValueError, match="unknown indicators"):
            indicator_series_view(make_bars(30), ("NOPE",))


class TestBarsEndpoints:
    @pytest.fixture()
    def client(self):
        state = DashboardState()
        state.marketdata = MarketDataService(make_registry(CountingFeed()))
        return TestClient(create_app(state))

    def test_symbols_capability_disclosure(self, client):
        payload = client.get("/api/symbols").json()
        assert payload[0]["symbol"] == "XAUUSD"
        assert payload[0]["timeframes"] == ["1d", "1h"]
        assert payload[0]["live"] is False

    def test_bars_endpoint(self, client):
        rows = client.get("/api/bars",
                          params={"symbol": "XAUUSD", "timeframe": "1d",
                                  "limit": 5}).json()
        assert len(rows) == 5 and "close" in rows[0]

    def test_error_mapping(self, client):
        assert client.get("/api/bars", params={"symbol": "DOGE"}).status_code == 404
        r = client.get("/api/bars", params={"symbol": "XAUUSD", "timeframe": "1m"})
        assert r.status_code == 404 and "available" in r.json()["detail"]
        assert client.get("/api/bars",
                          params={"symbol": "XAUUSD",
                                  "timeframe": "bogus"}).status_code == 422

    def test_vendor_unreachable_maps_to_503(self):
        class Unreachable(CountingFeed):
            def get_bars(self, *a, **k):
                raise ConnectionError("egress blocked")

        state = DashboardState()
        state.marketdata = MarketDataService(make_registry(Unreachable()))
        client = TestClient(create_app(state))
        response = client.get("/api/bars", params={"symbol": "XAUUSD"})
        assert response.status_code == 503
        assert "unreachable" in response.json()["detail"]

    def test_rate_limit_maps_to_503(self):
        class Throttled(CountingFeed):
            def get_bars(self, *a, **k):
                raise VendorRateLimitError("HTTP 429")

        state = DashboardState()
        state.marketdata = MarketDataService(make_registry(Throttled()))
        client = TestClient(create_app(state))
        response = client.get("/api/bars", params={"symbol": "XAUUSD"})
        assert response.status_code == 503
        assert response.headers["retry-after"] == "30"

    def test_indicator_endpoint(self, client):
        payload = client.get(
            "/api/bars/indicators",
            params={"symbol": "XAUUSD", "timeframe": "1d",
                    "names": "RSI_14", "limit": 60},
        ).json()
        assert "RSI_14" in payload and payload["RSI_14"]["params"] == {"period": 14}
        assert client.get(
            "/api/bars/indicators",
            params={"symbol": "XAUUSD", "names": "NOPE"},
        ).status_code == 422


class FakeOandaTransport:
    """Serves canned candle payloads keyed by granularity."""

    def __init__(self):
        self.requests = []

    def get_json(self, url, params=None):
        self.requests.append((url, params))
        granularity = params["granularity"]
        if granularity == "S5":
            return {"candles": [{
                "time": "2026-07-08T10:00:00.000000000Z", "complete": False,
                "bid": {"c": "4066.5"}, "ask": {"c": "4067.5"},
                "mid": {"o": "4067", "h": "4067", "l": "4066", "c": "4067.0"},
            }]}
        candles = []
        for i in range(int(params["count"])):
            candles.append({
                "time": (BASE_TS + timedelta(hours=i)).isoformat().replace("+00:00", "Z"),
                "complete": i < int(params["count"]) - 1,  # last one incomplete
                "volume": 100 + i,
                "mid": {"o": "4000", "h": "4010", "l": "3990",
                        "c": str(4000 + i)},
            })
        return {"candles": candles}


class TestOandaGoldFeed:
    def test_requires_token(self, monkeypatch):
        monkeypatch.delenv("OANDA_API_TOKEN", raising=False)
        assert OandaGoldFeed.configured() is False
        with pytest.raises(OandaNotConfiguredError):
            OandaGoldFeed()

    def test_bars_drop_incomplete_and_map_granularity(self):
        transport = FakeOandaTransport()
        feed = OandaGoldFeed(transport=transport, token="t")
        bars = feed.get_bars("XAU_USD", Timeframe.H1, limit=5)
        assert len(bars) == 5
        assert all(isinstance(b, OHLCVBar) for b in bars)
        url, params = transport.requests[0]
        assert "instruments/XAU_USD/candles" in url
        assert params["granularity"] == "H1" and params["price"] == "M"
        # requested limit+1 so the dropped incomplete candle doesn't short us
        assert params["count"] == 6

    def test_empty_payload_raises_no_market_data(self):
        empty = OandaGoldFeed(transport=type("T", (), {
            "get_json": lambda self, url, params=None: {"candles": []}
        })(), token="t")
        with pytest.raises(NoMarketDataError):
            empty.get_bars("XAU_USD", Timeframe.H1)

    def test_quote_from_bid_ask_candle(self):
        feed = OandaGoldFeed(transport=FakeOandaTransport(), token="t")
        quote = feed.get_quote("XAU_USD")
        assert quote.bid == 4066.5 and quote.ask == 4067.5 and quote.last == 4067.0

    def test_bad_env_rejected(self):
        with pytest.raises(ValueError, match="OANDA_ENV"):
            OandaGoldFeed(transport=FakeOandaTransport(), token="t", env="staging")


class TestGoldTickPoller:
    def test_skips_vendor_when_no_subscribers(self):
        feed = OandaGoldFeed(transport=FakeOandaTransport(), token="t")
        broadcaster = EventBroadcaster()
        poller = GoldTickPoller(feed, broadcaster)
        assert poller.poll_once() is False  # zero subscribers -> zero requests

    def test_publishes_tick_when_subscribed(self):
        import asyncio

        feed = OandaGoldFeed(transport=FakeOandaTransport(), token="t")
        broadcaster = EventBroadcaster()
        poller = GoldTickPoller(feed, broadcaster)

        async def scenario():
            broadcaster.bind_loop(asyncio.get_running_loop())
            agen = broadcaster.subscribe(None)
            pull = asyncio.ensure_future(agen.__anext__())
            await asyncio.sleep(0)
            assert poller.poll_once() is True
            frame = await pull
            await agen.aclose()
            return frame

        frame = asyncio.run(scenario())
        assert "event: tick" in frame and '"symbol": "XAUUSD"' in frame

    def test_thread_start_stop(self):
        feed = OandaGoldFeed(transport=FakeOandaTransport(), token="t")
        poller = GoldTickPoller(feed, EventBroadcaster(), interval=0.01)
        poller.start()
        poller.stop()
        assert poller._thread is None


class TestRegistryFallback:
    def test_invalid_oanda_token_falls_back_to_yfinance(self, monkeypatch):
        from tradingagents.pro.dashboard.marketdata import default_registry
        from tradingagents.pro.ingestion.delta_exchange import DeltaExchangeFeed
        from tradingagents.pro.ingestion.oanda_gold import OandaGoldFeed

        monkeypatch.setenv("OANDA_API_TOKEN", "configured-but-invalid")
        monkeypatch.setattr(DeltaExchangeFeed, "probe", classmethod(lambda cls, timeout=8.0: False))
        monkeypatch.setattr(OandaGoldFeed, "probe", classmethod(lambda cls, timeout=8.0: False))
        registry = default_registry()
        assert registry["XAUUSD"].source == "yfinance_daily"
        assert registry["XAUUSD"].live is False

    def test_valid_probe_enables_oanda(self, monkeypatch):
        from tradingagents.pro.dashboard.marketdata import default_registry
        from tradingagents.pro.ingestion.delta_exchange import DeltaExchangeFeed
        from tradingagents.pro.ingestion.oanda_gold import OandaGoldFeed

        monkeypatch.setenv("OANDA_API_TOKEN", "valid")
        monkeypatch.setattr(DeltaExchangeFeed, "probe", classmethod(lambda cls, timeout=8.0: False))
        monkeypatch.setattr(OandaGoldFeed, "probe", classmethod(lambda cls, timeout=8.0: True))
        registry = default_registry()
        assert registry["XAUUSD"].source == "oanda_gold"
        assert registry["XAUUSD"].live is True
        assert "1h" in registry["XAUUSD"].timeframes


class TestDeltaPreference:
    def test_delta_serves_both_symbols_when_alive(self, monkeypatch):
        from tradingagents.pro.dashboard.marketdata import default_registry
        from tradingagents.pro.ingestion.delta_exchange import DeltaExchangeFeed

        monkeypatch.setattr(DeltaExchangeFeed, "probe",
                            classmethod(lambda cls, timeout=8.0: True))
        registry = default_registry()
        assert registry["BTC-USD"].source == "delta_exchange"
        assert registry["BTC-USD"].vendor_symbol == "BTCUSD"
        assert registry["XAUUSD"].source == "delta_exchange"
        assert registry["XAUUSD"].vendor_symbol == "PAXGUSD"
        assert registry["XAUUSD"].live is True
        assert "1m" in [t.value for t in registry["XAUUSD"].timeframes]

    def test_kill_switch_env_forces_fallbacks(self, monkeypatch):
        from tradingagents.pro.dashboard.marketdata import default_registry
        from tradingagents.pro.ingestion.delta_exchange import DeltaExchangeFeed

        monkeypatch.setenv("PRO_DISABLE_LIVE_VENDORS", "1")
        monkeypatch.delenv("OANDA_API_TOKEN", raising=False)
        assert DeltaExchangeFeed.probe() is False  # no network touched
        registry = default_registry()
        assert registry["BTC-USD"].source == "binance_spot"
        assert registry["XAUUSD"].source == "yfinance_daily"
