"""Trader-review G4 (price alerts), G6 (news), G7 (parameterized indicators)."""

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.dashboard.prefs import PrefsStore
from tradingagents.pro.dashboard.ticker import PriceAlertEngine, TickCache
from tradingagents.pro.ingestion.indicators import (
    compute_indicator_series,
    compute_indicators,
)
from tradingagents.pro.ingestion.news import YahooFinanceNewsFeed, _item_from_yf

BASE = datetime(2026, 7, 1, tzinfo=timezone.utc)


def bars(closes, timeframe=Timeframe.H1, volumes=None, start=BASE):
    step = timedelta(hours=1) if timeframe == Timeframe.H1 else timedelta(days=1)
    out = []
    for i, close in enumerate(closes):
        out.append(OHLCVBar(
            timeframe=timeframe, start=start + i * step,
            open=close, high=close * 1.001, low=close * 0.999, close=close,
            volume=(volumes[i] if volumes else 100.0),
        ))
    return out


# --- G4: price alerts -----------------------------------------------------------


@pytest.fixture()
def store(tmp_path):
    return PrefsStore(tmp_path / "prefs.json")


class TestPriceAlertStore:
    def test_crud_and_persistence(self, store, tmp_path):
        created = store.add_price_alert(
            {"symbol": "XAUUSD", "level": 4175.63, "direction": "above",
             "note": "AI invalidation level"})
        assert created["active"] is True and created["created_at"]
        assert store.has_active_price_alerts()
        # survives a reload (single JSON document, atomic write)
        reloaded = PrefsStore(tmp_path / "prefs.json")
        assert reloaded.price_alerts()[0]["level"] == 4175.63
        assert store.delete_price_alert(created["id"]) is True
        assert store.delete_price_alert(created["id"]) is False

    def test_validation(self, store):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            store.add_price_alert({"symbol": "XAUUSD", "level": -1,
                                   "direction": "above"})
        with pytest.raises(ValidationError):
            store.add_price_alert({"symbol": "XAUUSD", "level": 1,
                                   "direction": "sideways"})

    def test_cap_50(self, store):
        for i in range(50):
            store.add_price_alert({"symbol": "XAUUSD", "level": 1000 + i,
                                   "direction": "above"})
        with pytest.raises(ValueError, match="limit"):
            store.add_price_alert({"symbol": "XAUUSD", "level": 9999,
                                   "direction": "above"})


class TestPriceAlertEngine:
    def _engine(self, store):
        fired = []
        engine = PriceAlertEngine(
            store, lambda sev, event, text, **kw: fired.append((sev, event, text)))
        return engine, fired

    def test_cross_above_fires_once(self, store):
        store.add_price_alert({"symbol": "XAUUSD", "level": 4100.0,
                               "direction": "above"})
        engine, fired = self._engine(store)
        assert engine.check("XAUUSD", 4090.0, 4095.0) == 0   # no cross
        assert engine.check("XAUUSD", 4095.0, 4105.0) == 1   # crossed
        assert fired[0][1] == "price_alert" and "4100" in fired[0][2]
        # one-shot: deactivated, does not re-fire
        assert engine.check("XAUUSD", 4090.0, 4105.0) == 0
        assert not store.has_active_price_alerts()
        assert store.price_alerts()[0]["triggered_at"] is not None

    def test_cross_below(self, store):
        store.add_price_alert({"symbol": "XAUUSD", "level": 3962.0,
                               "direction": "below", "note": "June double low"})
        engine, fired = self._engine(store)
        assert engine.check("XAUUSD", 3970.0, 3960.0) == 1
        assert "June double low" in fired[0][2]

    def test_first_tick_only_seeds(self, store):
        store.add_price_alert({"symbol": "XAUUSD", "level": 4100.0,
                               "direction": "above"})
        engine, fired = self._engine(store)
        assert engine.check("XAUUSD", None, 4200.0) == 0  # no prev: no fire

    def test_symbol_isolation(self, store):
        store.add_price_alert({"symbol": "BTC-USD", "level": 63000.0,
                               "direction": "above"})
        engine, fired = self._engine(store)
        assert engine.check("XAUUSD", 62000.0, 64000.0) == 0

    def test_emit_failure_never_reactivates(self, store):
        store.add_price_alert({"symbol": "XAUUSD", "level": 4100.0,
                               "direction": "above"})

        def boom(*a, **k):
            raise RuntimeError("sink down")

        engine = PriceAlertEngine(store, boom)
        engine.check("XAUUSD", 4095.0, 4105.0)
        assert not store.has_active_price_alerts()  # fail-closed, no spam


class TestTickCache:
    def test_put_get(self):
        cache = TickCache()
        assert cache.get("XAUUSD") is None
        cache.put("XAUUSD", 4000.0, "t1")
        assert cache.get("XAUUSD") == (4000.0, "t1")


# --- G6: news feed ---------------------------------------------------------------


class TestNewsFeed:
    def test_new_shape_normalized(self):
        raw = {"content": {
            "title": "Gold slides as yields rise",
            "summary": "Bullion fell...",
            "pubDate": "2026-07-13T14:00:00Z",
            "provider": {"displayName": "Reuters"},
            "canonicalUrl": {"url": "https://example.com/x"},
        }}
        item = _item_from_yf(raw)
        assert item.headline.startswith("Gold slides")
        assert item.source == "Reuters"
        assert item.published_at.year == 2026
        assert item.url == "https://example.com/x"

    def test_legacy_shape_and_garbage(self):
        legacy = {"title": "BTC rallies", "publisher": "CoinDesk",
                  "link": "https://example.com/y",
                  "providerPublishTime": 1780000000}
        assert _item_from_yf(legacy).source == "CoinDesk"
        assert _item_from_yf({"content": {"title": ""}}) is None

    def test_feed_limit_and_loader(self):
        rows = [{"title": f"headline {i}", "publisher": "T"} for i in range(30)]
        feed = YahooFinanceNewsFeed("GC=F", limit=5, loader=lambda t: rows)
        items = feed.get_news()
        assert len(items) == 5

    def test_hermetic_kill_switch(self, monkeypatch):
        monkeypatch.setenv("PRO_DISABLE_LIVE_VENDORS", "1")
        assert YahooFinanceNewsFeed("GC=F").get_news() == []

    def test_builder_wires_news(self):
        """Gold/BTC pipelines now carry a news feed; a raising vendor
        degrades like any other feed (missing_feeds gains its name)."""
        from tradingagents.pro.ingestion.builder import SnapshotBuilder

        class FakeBars:
            name = "fake_bars"

            def get_bars(self, symbol, timeframe, limit=250, end=None):
                return bars([100 + i for i in range(30)], Timeframe.D1)

        class GoodNews:
            name = "yahoo_news"

            def get_news(self):
                return [_item_from_yf({"title": "hi", "publisher": "T"})]

        class BadNews(GoodNews):
            def get_news(self):
                raise RuntimeError("offline")

        from tradingagents.contracts import AssetClass

        snapshot = SnapshotBuilder(bars_feed=FakeBars(),
                                   news_feed=GoodNews()).build(
            "XAUUSD", AssetClass.GOLD)
        assert len(snapshot.news) == 1
        assert "yahoo_news" not in snapshot.missing_feeds

        degraded = SnapshotBuilder(bars_feed=FakeBars(),
                                   news_feed=BadNews()).build(
            "XAUUSD", AssetClass.GOLD)
        assert degraded.news == []
        assert "yahoo_news" in degraded.missing_feeds


# --- G7: parameterized indicators + VWAP -----------------------------------------


class TestParameterizedIndicators:
    def test_custom_periods(self):
        series = compute_indicator_series(
            bars([100 + i * 0.5 for i in range(60)]), ["EMA_21", "RSI_9"])
        assert series["EMA_21"]["params"] == {"period": 21}
        values = series["EMA_21"]["series"]["value"]
        assert values[19] is None and values[21] is not None  # warm-up honored
        assert series["RSI_9"]["series"]["value"][-1] is not None

    def test_fixed_names_still_work(self):
        series = compute_indicator_series(
            bars([100 + i for i in range(60)]), ["EMA_10", "MACD"])
        assert set(series) == {"EMA_10", "MACD"}

    def test_bad_period_rejected(self):
        with pytest.raises(ValueError, match="period"):
            compute_indicator_series(bars([100] * 10), ["EMA_401"])
        with pytest.raises(ValueError, match="unknown indicator"):
            compute_indicator_series(bars([100] * 10), ["WIZARDRY_9"])

    def test_vwap_resets_each_utc_day(self):
        # two UTC days of hourly bars with distinct prices
        day1 = bars([100.0] * 24, volumes=[10.0] * 24)
        day2 = bars([200.0] * 24, volumes=[10.0] * 24,
                    start=BASE + timedelta(days=1))
        series = compute_indicator_series(day1 + day2, ["VWAP"])
        values = series["VWAP"]["series"]["value"]
        assert values[23] == pytest.approx(100.0, rel=1e-3)
        assert values[24] == pytest.approx(200.0, rel=1e-3)  # reset at day 2

    def test_vwap_rejects_daily(self):
        with pytest.raises(ValueError, match="intraday"):
            compute_indicator_series(
                bars([100] * 10, timeframe=Timeframe.D1), ["VWAP"])

    def test_vwap_zero_volume_is_null(self):
        series = compute_indicator_series(
            bars([100.0] * 5, volumes=[0.0] * 5), ["VWAP"])
        assert series["VWAP"]["series"]["value"] == [None] * 5

    def test_latest_value_path_supports_params(self):
        readings = compute_indicators(
            bars([100 + i * 0.5 for i in range(60)]), ["EMA_21", "VWAP"])
        names = {r.name for r in readings}
        assert names == {"EMA_21", "VWAP"}
