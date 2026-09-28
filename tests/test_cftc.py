"""CFTC COT vendor: release-lag safety, formatting, resilience, and routing."""

import copy
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
import requests

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import router
from tradingagents.dataflows.config import run_config, set_config
from tradingagents.dataflows.vendors import cftc


def _tff_row(report_date: str, *, lev_long: int, lev_short: int, oi: int = 100_000) -> dict:
    return {
        "market_and_exchange_names": "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
        "report_date_as_yyyy_mm_dd": f"{report_date}T00:00:00.000",
        "open_interest_all": str(oi),
        "change_in_open_interest_all": "100",
        "dealer_positions_long_all": "1000",
        "dealer_positions_short_all": "1200",
        "change_in_dealer_long_all": "10",
        "change_in_dealer_short_all": "-5",
        "pct_of_oi_dealer_long_all": "1.0",
        "pct_of_oi_dealer_short_all": "1.2",
        "asset_mgr_positions_long": "5000",
        "asset_mgr_positions_short": "4000",
        "change_in_asset_mgr_long": "20",
        "change_in_asset_mgr_short": "25",
        "pct_of_oi_asset_mgr_long": "5.0",
        "pct_of_oi_asset_mgr_short": "4.0",
        "lev_money_positions_long": str(lev_long),
        "lev_money_positions_short": str(lev_short),
        "change_in_lev_money_long": "50",
        "change_in_lev_money_short": "-25",
        "pct_of_oi_lev_money_long": str(round(100 * lev_long / oi, 1)),
        "pct_of_oi_lev_money_short": str(round(100 * lev_short / oi, 1)),
        "other_rept_positions_long": "3000",
        "other_rept_positions_short": "3100",
        "change_in_other_rept_long": "0",
        "change_in_other_rept_short": "10",
        "pct_of_oi_other_rept_long": "3.0",
        "pct_of_oi_other_rept_short": "3.1",
    }


@pytest.mark.unit
class CftcVendorTests(unittest.TestCase):
    def test_release_lag_blocks_unpublished_tuesday_snapshot(self):
        rows = [
            _tff_row("2026-09-22", lev_long=10_000, lev_short=8_000),
            _tff_row("2026-09-15", lev_long=9_000, lev_short=8_500),
        ]

        def _fake_request(dataset_id, query):
            if dataset_id == "yw9f-hn96":
                return rows
            return []

        with tempfile.TemporaryDirectory() as cache_dir, \
                run_config({"data_cache_dir": cache_dir}), \
                mock.patch.object(cftc, "_request", side_effect=_fake_request):
            out = cftc.get_commitments_of_traders(
                "E-MINI S&P 500", look_back_weeks=8, curr_date="2026-09-24"
            )

        assert "Latest released report date (Tuesday snapshot): 2026-09-15" in out
        assert "2026-09-22" not in out

    def test_report_includes_net_and_weekly_change(self):
        rows = [
            _tff_row("2026-09-22", lev_long=10_000, lev_short=8_000),
            _tff_row("2026-09-15", lev_long=9_000, lev_short=8_500),
        ]

        def _fake_request(dataset_id, query):
            if dataset_id == "yw9f-hn96":
                return rows
            return []

        with tempfile.TemporaryDirectory() as cache_dir, \
                run_config({"data_cache_dir": cache_dir}), \
                mock.patch.object(cftc, "_request", side_effect=_fake_request):
            out = cftc.get_commitments_of_traders(
                "E-MINI S&P 500", look_back_weeks=8, curr_date="2026-09-27"
            )

        assert "| Leveraged Funds | 10,000 | 8,000 | +2,000 | +1,500 |" in out
        assert "### Positioning read-through" in out

    def test_no_match_returns_guidance(self):
        with tempfile.TemporaryDirectory() as cache_dir, \
                run_config({"data_cache_dir": cache_dir}), \
                mock.patch.object(cftc, "_request", return_value=[]):
            out = cftc.get_commitments_of_traders("NVDA", look_back_weeks=12, curr_date="2026-09-27")

        assert "No released CFTC COT market matched" in out
        assert "'NVDA'" in out

    def test_network_error_degrades_gracefully(self):
        with tempfile.TemporaryDirectory() as cache_dir, \
                run_config({"data_cache_dir": cache_dir}), \
                mock.patch.object(cftc, "_request", side_effect=requests.RequestException("boom")):
            out = cftc.get_commitments_of_traders("E-MINI S&P 500", curr_date="2026-09-27")

        assert "unavailable" in out.lower()
        assert "boom" in out

    def test_cache_reuses_payload_within_same_release_window(self):
        rows = [_tff_row("2026-09-22", lev_long=10_000, lev_short=8_000)]
        calls = {"count": 0}

        def _fake_request(dataset_id, query):
            calls["count"] += 1
            return rows

        with tempfile.TemporaryDirectory() as cache_dir, \
                run_config({"data_cache_dir": cache_dir}), \
                mock.patch.object(cftc, "DATASETS", (cftc.DATASETS[0],)), \
                mock.patch.object(cftc, "_request", side_effect=_fake_request):
            cftc.get_commitments_of_traders("E-MINI S&P 500", look_back_weeks=8, curr_date="2026-09-27")
            cftc.get_commitments_of_traders("E-MINI S&P 500", look_back_weeks=8, curr_date="2026-09-27")

        assert calls["count"] == 1

    def test_cache_refreshes_when_a_new_release_is_expected(self):
        old_rows = [_tff_row("2026-09-15", lev_long=9_000, lev_short=8_500)]
        new_rows = [_tff_row("2026-09-22", lev_long=10_000, lev_short=8_000)]
        sequence = [old_rows, new_rows]

        def _fake_request(dataset_id, query):
            return sequence.pop(0)

        with tempfile.TemporaryDirectory() as cache_dir, \
                run_config({"data_cache_dir": cache_dir}), \
                mock.patch.object(cftc, "DATASETS", (cftc.DATASETS[0],)), \
                mock.patch.object(cftc, "_request", side_effect=_fake_request):
            out1 = cftc.get_commitments_of_traders("E-MINI S&P 500", curr_date="2026-09-24")
            out2 = cftc.get_commitments_of_traders("E-MINI S&P 500", curr_date="2026-09-27")

        assert "2026-09-15" in out1
        assert "2026-09-22" in out2
        assert sequence == []

    def test_stale_cache_is_used_when_refresh_fails(self):
        old_rows = [_tff_row("2026-09-15", lev_long=9_000, lev_short=8_500)]

        with tempfile.TemporaryDirectory() as cache_dir:
            with run_config({"data_cache_dir": cache_dir}), \
                    mock.patch.object(cftc, "DATASETS", (cftc.DATASETS[0],)), \
                    mock.patch.object(cftc, "_request", return_value=old_rows):
                cftc.get_commitments_of_traders("E-MINI S&P 500", curr_date="2026-09-24")

            with run_config({"data_cache_dir": cache_dir}), \
                    mock.patch.object(cftc, "DATASETS", (cftc.DATASETS[0],)), \
                    mock.patch.object(cftc, "_request", side_effect=requests.RequestException("outage")):
                out = cftc.get_commitments_of_traders("E-MINI S&P 500", curr_date="2026-09-27")

        assert "2026-09-15" in out
        assert "unavailable" not in out.lower()

    def test_cache_can_be_disabled(self):
        rows = [_tff_row("2026-09-22", lev_long=10_000, lev_short=8_000)]
        calls = {"count": 0}

        def _fake_request(dataset_id, query):
            calls["count"] += 1
            return rows

        with tempfile.TemporaryDirectory() as cache_dir, \
                run_config({"data_cache_dir": cache_dir, "cftc_cache_enabled": False}), \
                mock.patch.object(cftc, "DATASETS", (cftc.DATASETS[0],)), \
                mock.patch.object(cftc, "_request", side_effect=_fake_request):
            cftc.get_commitments_of_traders("E-MINI S&P 500", curr_date="2026-09-27")
            cftc.get_commitments_of_traders("E-MINI S&P 500", curr_date="2026-09-27")

            cache_path = os.path.join(cache_dir, cftc.CACHE_SUBDIR)
            assert not os.path.exists(cache_path)

        assert calls["count"] == 2

    def test_cache_retention_prunes_old_files(self):
        rows = [_tff_row("2026-09-22", lev_long=10_000, lev_short=8_000)]

        with tempfile.TemporaryDirectory() as cache_dir:
            cache_subdir = os.path.join(cache_dir, cftc.CACHE_SUBDIR)
            os.makedirs(cache_subdir, exist_ok=True)
            stale_file = os.path.join(cache_subdir, "stale.json")
            with open(stale_file, "w", encoding="utf-8") as f:
                f.write("{}")
            stale_time = (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()
            os.utime(stale_file, (stale_time, stale_time))

            with run_config({
                "data_cache_dir": cache_dir,
                "cftc_cache_max_age_days": 1,
            }), \
                    mock.patch.object(cftc, "DATASETS", (cftc.DATASETS[0],)), \
                    mock.patch.object(cftc, "_request", return_value=rows):
                cftc.get_commitments_of_traders("E-MINI S&P 500", curr_date="2026-09-27")

            assert not os.path.exists(stale_file)


@pytest.mark.unit
class CftcRoutingTests(unittest.TestCase):
    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def test_category_routes_to_cftc(self):
        self.assertEqual(
            router.get_category_for_method("get_commitments_of_traders"),
            "positioning_data",
        )
        set_config({"data_vendors": {"positioning_data": "cftc"}})
        with mock.patch.dict(
            router.VENDOR_METHODS,
            {"get_commitments_of_traders": {"cftc": lambda *a, **k: "COT_OK"}},
            clear=False,
        ):
            out = router.route_to_vendor("get_commitments_of_traders", "E-MINI S&P 500", 8, "2026-09-27")
        self.assertEqual(out, "COT_OK")
