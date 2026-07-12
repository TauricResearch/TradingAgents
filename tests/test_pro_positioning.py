"""DR-1: CFTC COT positioning + GVZ implied-vol feeds."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.pro_fakes import FakeTransport
from tests.test_pro_gold_feeds import make_feed
from tradingagents.pro.ingestion.positioning import GoldCotFeed, GoldVolFeed

COT_ROWS = [
    {"report_date_as_yyyy_mm_dd": "2026-07-07T00:00:00.000",
     "noncomm_positions_long_all": "233713",
     "noncomm_positions_short_all": "39467",
     "open_interest_all": "371776"},
    {"report_date_as_yyyy_mm_dd": "2026-06-30T00:00:00.000",
     "noncomm_positions_long_all": "229619",
     "noncomm_positions_short_all": "35600",
     "open_interest_all": "369541"},
]


def _fresh_rows():
    """COT_ROWS with the latest report re-dated inside the cache window."""
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).strftime(
        "%Y-%m-%dT00:00:00.000")
    rows = [dict(COT_ROWS[0], report_date_as_yyyy_mm_dd=recent), COT_ROWS[1]]
    return rows


class TestGoldCotFeed:
    def test_metrics_from_report(self):
        feed = GoldCotFeed(transport=FakeTransport(
            {"publicreporting.cftc.gov": COT_ROWS}))
        readings = {m.name: m for m in feed.get_metrics()}
        assert readings["GOLD_COT_NET_NONCOMM"].value == 233713 - 39467
        assert readings["GOLD_COT_NET_CHANGE_1W"].value == pytest.approx(
            (233713 - 39467) - (229619 - 35600))
        assert readings["GOLD_COT_NET_PCT_OI"].value == pytest.approx(
            100 * (233713 - 39467) / 371776)
        assert readings["GOLD_COT_NET_NONCOMM"].as_of.year == 2026
        assert readings["GOLD_COT_NET_NONCOMM"].unit == "contracts"

    def test_cache_serves_within_weekly_window(self, tmp_path):
        cache = tmp_path / "cot.json"
        good = GoldCotFeed(transport=FakeTransport(
            {"publicreporting.cftc.gov": _fresh_rows()}), cache_path=cache)
        good.get_metrics()
        assert cache.exists()

        class DeadTransport:
            def get_json(self, url, params=None):
                raise ConnectionError("cftc down")

        degraded = GoldCotFeed(transport=DeadTransport(), cache_path=cache)
        readings = {m.name for m in degraded.get_metrics()}
        assert "GOLD_COT_NET_NONCOMM" in readings  # cache = fresh data

    def test_stale_cache_is_degradation_not_data(self, tmp_path):
        cache = tmp_path / "cot.json"
        ancient = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
            "%Y-%m-%dT00:00:00.000")
        stale_rows = [dict(COT_ROWS[0], report_date_as_yyyy_mm_dd=ancient)]
        old = GoldCotFeed(transport=FakeTransport(
            {"publicreporting.cftc.gov": stale_rows}), cache_path=cache)
        old.get_metrics()  # cache now holds a month-old report

        class DeadTransport:
            def get_json(self, url, params=None):
                raise ConnectionError("cftc down")

        degraded = GoldCotFeed(transport=DeadTransport(), cache_path=cache)
        with pytest.raises(ConnectionError):
            degraded.get_metrics()  # stale report must NOT be served

    def test_probe_refuses_under_hermetic_env(self, monkeypatch):
        monkeypatch.setenv("PRO_DISABLE_LIVE_VENDORS", "1")
        assert GoldCotFeed.probe() is False


class TestGoldVolFeed:
    def test_metrics_from_bars(self):
        feed = GoldVolFeed(make_feed())  # fake loader includes ^GVZ
        readings = {m.name: m for m in feed.get_metrics()}
        assert readings["GOLD_VOL_INDEX"].value > 0
        assert "GOLD_VOL_INDEX_CHANGE_1D" in readings
        assert readings["GOLD_VOL_INDEX"].unit == "vol_points"

    def test_probe_refuses_under_hermetic_env(self, monkeypatch):
        monkeypatch.setenv("PRO_DISABLE_LIVE_VENDORS", "1")
        assert GoldVolFeed.probe() is False


class TestRosterConsumption:
    def test_gold_macro_agents_request_new_metrics(self):
        from tradingagents.pro.agents.roster import MACRO_SPECS

        by_id = {spec.agent_id: spec for spec in MACRO_SPECS}
        assert "GOLD_COT_NET_NONCOMM" in by_id["cot_positioning"].metrics
        assert "GOLD_VOL_INDEX" in by_id["implied_volatility"].metrics
