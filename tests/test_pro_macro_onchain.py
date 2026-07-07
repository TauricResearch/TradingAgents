"""FRED macro + on-chain/sentiment feeds against canned payloads."""

import pytest

from tests.pro_fakes import FakeTransport
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.fred import FredNotConfiguredError
from tradingagents.pro.ingestion.fred_macro import FredMacroFeed
from tradingagents.pro.ingestion.onchain import BlockchainComFeed, CoinMetricsFeed, FearGreedFeed


class TestFredMacro:
    def fred_payload(self, params):
        series = params["series_id"]
        values = {
            "DGS10": "4.25",
            "CPIAUCSL": "2.9",
        }
        return {
            "observations": [
                {"date": "2026-07-06", "value": "."},  # leading placeholder
                {"date": "2026-07-03", "value": values.get(series, "1.0")},
            ]
        }

    def make_feed(self, series=None):
        transport = FakeTransport({"/fred/series/observations": self.fred_payload})
        return FredMacroFeed(transport=transport, api_key="test-key", series=series)

    def test_skips_placeholder_and_reads_latest_real_value(self):
        feed = self.make_feed(series={"US10Y": ("DGS10", "lin", "percent")})
        readings = {r.name: r for r in feed.get_metrics()}
        assert readings["US10Y"].value == pytest.approx(4.25)
        assert readings["US10Y"].source == "fred:DGS10"
        assert readings["US10Y"].as_of.tzinfo is not None

    def test_yoy_transform_requested_server_side(self):
        transport = FakeTransport({"/fred/series/observations": self.fred_payload})
        feed = FredMacroFeed(
            transport=transport, api_key="k", series={"CPI_YOY": ("CPIAUCSL", "pc1", "percent")}
        )
        feed.get_metrics()
        _, params = transport.calls[0]
        assert params["units"] == "pc1"

    def test_missing_key_raises_not_configured(self, monkeypatch):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        with pytest.raises(FredNotConfiguredError):
            FredMacroFeed(transport=FakeTransport({})).get_metrics()


class TestCoinMetrics:
    PAYLOAD = {
        "data": [
            {
                "asset": "btc",
                "time": "2026-07-06T00:00:00.000000000Z",
                "CapMVRVCur": "2.1345",
                "CapRealUSD": "650000000000",
                "AdrActCnt": "912345",
            }
        ]
    }

    def test_maps_community_metrics(self):
        feed = CoinMetricsFeed(transport=FakeTransport({"asset-metrics": self.PAYLOAD}))
        readings = {r.name: r for r in feed.get_metrics()}
        assert readings["MVRV"].value == pytest.approx(2.1345)
        assert readings["REALIZED_CAP_USD"].value == pytest.approx(6.5e11)
        assert readings["ACTIVE_ADDRESSES"].value == pytest.approx(912345)

    def test_empty_data_raises(self):
        feed = CoinMetricsFeed(transport=FakeTransport({"asset-metrics": {"data": []}}))
        with pytest.raises(NoMarketDataError):
            feed.get_metrics()


class TestBlockchainCom:
    ROUTES = {
        "charts/hash-rate": {"values": [{"x": 1751500800, "y": 7.5e8}]},
        "charts/miners-revenue": {"values": [{"x": 1751500800, "y": 4.2e7}]},
    }

    def test_reads_latest_chart_points(self):
        feed = BlockchainComFeed(transport=FakeTransport(self.ROUTES))
        readings = {r.name: r for r in feed.get_metrics()}
        assert readings["HASH_RATE"].value == pytest.approx(7.5e8)
        assert readings["MINERS_REVENUE_USD"].unit == "USD"

    def test_all_empty_raises(self):
        empty = {"charts/hash-rate": {"values": []}, "charts/miners-revenue": {"values": []}}
        with pytest.raises(NoMarketDataError):
            BlockchainComFeed(transport=FakeTransport(empty)).get_metrics()


class TestFearGreed:
    def test_reads_index(self):
        payload = {"data": [{"value": "72", "timestamp": "1751846400"}]}
        feed = FearGreedFeed(transport=FakeTransport({"fng": payload}))
        (reading,) = feed.get_metrics()
        assert reading.name == "FEAR_GREED_INDEX"
        assert reading.value == 72.0

    def test_empty_raises(self):
        feed = FearGreedFeed(transport=FakeTransport({"fng": {"data": []}}))
        with pytest.raises(NoMarketDataError):
            feed.get_metrics()
