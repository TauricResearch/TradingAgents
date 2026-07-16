"""SnapshotBuilder composition, failure absorption, and end-to-end pipelines."""

from datetime import datetime, timezone

import pytest

from tests.pro_fakes import FakeBarsFeed, FakeTransport
from tests.test_pro_binance import ROUTES as BINANCE_ROUTES
from tests.test_pro_gold_feeds import fake_loader
from tests.test_pro_macro_onchain import TestBlockchainCom, TestCoinMetrics
from tradingagents.contracts import (
    AssetClass,
    MarketSnapshot,
    MetricReading,
    Timeframe,
    TradingSession,
)
from tradingagents.pro.ingestion.builder import (
    SnapshotBuilder,
    build_bitcoin_pipeline,
    build_gold_pipeline,
)

AS_OF = datetime(2026, 7, 6, 14, 30, tzinfo=timezone.utc)


class GoodMetrics:
    name = "good_metrics"

    def get_metrics(self):
        return [
            MetricReading(name="DXY", value=104.2, as_of=AS_OF, source=self.name),
        ]


class FailingMetrics:
    name = "failing_metrics"

    def get_metrics(self):
        raise RuntimeError("vendor exploded")


class FailingQuote:
    name = "failing_quote"

    def get_quote(self, symbol):
        raise RuntimeError("quote down")


def test_builder_composes_full_snapshot():
    builder = SnapshotBuilder(
        bars_feed=FakeBarsFeed(),
        macro_feeds=(GoodMetrics(),),
        session_fn=lambda ts: TradingSession.NEW_YORK,
    )
    snapshot = builder.build("XAUUSD", AssetClass.GOLD, as_of=AS_OF)

    assert isinstance(snapshot, MarketSnapshot)
    assert snapshot.symbol == "XAUUSD"
    assert len(snapshot.bars) == 60
    assert snapshot.get_indicator("RSI_14", Timeframe.D1) is not None
    assert snapshot.macro[0].name == "DXY"
    assert snapshot.session is TradingSession.NEW_YORK
    assert snapshot.missing_feeds == []


def test_feed_failures_land_in_missing_feeds_not_exceptions():
    builder = SnapshotBuilder(
        bars_feed=FakeBarsFeed(),
        quote_feed=FailingQuote(),
        macro_feeds=(FailingMetrics(), GoodMetrics()),
        extra_metric_fns=(lambda: (_ for _ in ()).throw(RuntimeError("boom")),),
    )
    snapshot = builder.build("XAUUSD", AssetClass.GOLD, as_of=AS_OF)

    assert "failing_quote" in snapshot.missing_feeds
    assert "failing_metrics" in snapshot.missing_feeds
    assert len(snapshot.missing_feeds) == 3
    assert snapshot.quote is None
    # the healthy feed still contributed
    assert [m.name for m in snapshot.macro] == ["DXY"]


def test_bar_failure_raises_no_snapshot_without_prices():
    class DeadBars:
        name = "dead_bars"

        def get_bars(self, *a, **k):
            raise RuntimeError("no prices")

    builder = SnapshotBuilder(bars_feed=DeadBars())
    with pytest.raises(RuntimeError, match="no prices"):
        builder.build("XAUUSD", AssetClass.GOLD, as_of=AS_OF)


def test_snapshot_round_trips_through_json():
    snapshot = SnapshotBuilder(bars_feed=FakeBarsFeed()).build(
        "XAUUSD", AssetClass.GOLD, as_of=AS_OF
    )
    restored = MarketSnapshot.model_validate_json(snapshot.model_dump_json())
    assert restored == snapshot


def test_gold_pipeline_end_to_end_with_fakes(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    fred_payload = {
        "observations": [{"date": "2026-07-03", "value": "4.25"}]
    }
    cot_payload = [
        {"report_date_as_yyyy_mm_dd": "2026-07-07T00:00:00.000",
         "noncomm_positions_long_all": "233713",
         "noncomm_positions_short_all": "39467",
         "open_interest_all": "371776"},
        {"report_date_as_yyyy_mm_dd": "2026-06-30T00:00:00.000",
         "noncomm_positions_long_all": "229619",
         "noncomm_positions_short_all": "35600",
         "open_interest_all": "369541"},
    ]
    transport = FakeTransport({
        "/fred/series/observations": fred_payload,
        "publicreporting.cftc.gov": cot_payload,
    })

    builder = build_gold_pipeline(loader=fake_loader, transport=transport)
    snapshot = builder.build("GC=F", AssetClass.GOLD, bar_limit=40, as_of=AS_OF)

    assert snapshot.asset is AssetClass.GOLD
    assert snapshot.session is TradingSession.NEW_YORK  # Monday 14:30 UTC
    macro_names = {m.name for m in snapshot.macro}
    assert "XAU_XAG_CORR_30D" in macro_names
    assert "US10Y" in macro_names
    assert "GOLD_COT_NET_NONCOMM" in macro_names  # DR-1 positioning
    assert "GOLD_VOL_INDEX" in macro_names        # DR-1 implied vol
    # hermetic run: live vendors disabled -> the wired news feed returns
    # nothing, and a wired-but-empty feed is DISCLOSED (review P1.3)
    assert snapshot.missing_feeds == ["yahoo_news:empty"]


def test_bitcoin_pipeline_end_to_end_with_fakes():
    routes = {
        **BINANCE_ROUTES,
        "asset-metrics": TestCoinMetrics.PAYLOAD,
        **TestBlockchainCom.ROUTES,
        "fng": {"data": [{"value": "72", "timestamp": "1751846400"}]},
    }
    builder = build_bitcoin_pipeline(transport=FakeTransport(routes))
    snapshot = builder.build(
        "BTCUSDT", AssetClass.BITCOIN, timeframes=(Timeframe.H1,), bar_limit=2, as_of=AS_OF
    )

    assert snapshot.quote is not None and snapshot.quote.last == 60790.5
    macro_names = {m.name for m in snapshot.macro}
    assert {"FUNDING_RATE", "OPEN_INTEREST", "MARK_PRICE"} <= macro_names
    onchain_names = {m.name for m in snapshot.onchain}
    assert {"MVRV", "HASH_RATE", "FEAR_GREED_INDEX", "ORDERBOOK_IMBALANCE_100"} <= onchain_names
    # wired-but-empty news is disclosed, never silent (review P1.3)
    assert snapshot.missing_feeds == ["yahoo_news:empty"]
    assert snapshot.session is None  # crypto: no session concept


def test_bitcoin_pipeline_degrades_gracefully_when_onchain_dies():
    routes = {
        **BINANCE_ROUTES,
        # coinmetrics / blockchain.com / fng unrouted -> raise in FakeTransport
    }

    class PartialTransport(FakeTransport):
        def get_json(self, url, params=None):
            try:
                return super().get_json(url, params)
            except AssertionError:
                raise RuntimeError("service down") from None

    builder = build_bitcoin_pipeline(transport=PartialTransport(routes))
    snapshot = builder.build(
        "BTCUSDT", AssetClass.BITCOIN, timeframes=(Timeframe.H1,), bar_limit=2, as_of=AS_OF
    )
    assert {"coinmetrics_community", "blockchain_com", "fear_greed"} <= set(
        snapshot.missing_feeds
    )
    # bars and derivatives still present
    assert snapshot.bars and snapshot.macro
