"""Bank Negara Malaysia macro vendor: alias resolution, the OPR step-series
semantics, FX rendering, tolerant field parsing, lookahead safety, and the
router fallthrough to FRED for US series.

All API access is mocked, so these run without a network connection or a key.
"""
import copy
from unittest import mock

import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows import bnm, interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import NoMarketDataError

# Two OPR decisions in 2025 and one in 2024, the shape BNM's /opr/year/{y}
# endpoint returns.
_OPR_2024 = {"data": [{"date": "2024-05-09", "change_in_opr": 0.00, "new_opr_level": 3.00}]}
_OPR_2025 = {
    "data": [
        {"date": "2025-07-09", "change_in_opr": -0.25, "new_opr_level": 2.75},
        {"date": "2025-11-06", "change_in_opr": 0.00, "new_opr_level": 2.75},
    ]
}
_FX = {
    "data": [
        {"date": "2025-09-01", "rate": 4.2150},
        {"date": "2025-09-02", "rate": 4.2300},
    ]
}


def _request_stub(mapping, default=None):
    """Build a _request replacement dispatching on the endpoint path."""
    def _impl(path):
        for fragment, payload in mapping.items():
            if fragment in path:
                return payload
        return default if default is not None else {}
    return _impl


@pytest.mark.unit
class TestAliasResolution:
    @pytest.mark.parametrize(
        "alias", ["opr", "OPR", "policy_rate", "overnight policy rate", "malaysia-policy-rate"]
    )
    def test_opr_aliases_normalize(self, alias):
        assert bnm._resolve_series(alias) == bnm._OPR

    @pytest.mark.parametrize("alias", ["usd_myr", "ringgit", "MYR", "usdmyr"])
    def test_fx_aliases_normalize(self, alias):
        assert bnm._resolve_series(alias) == bnm._USDMYR

    def test_us_indicator_rejected_without_network(self):
        """A US series must be refused locally so the router falls to FRED."""
        with (
            mock.patch.object(bnm, "_request", side_effect=AssertionError("no network")),
            pytest.raises(NoMarketDataError) as exc,
        ):
            bnm.get_macro_data("fed_funds_rate", "2025-09-16")
        assert "FRED" in exc.value.detail


@pytest.mark.unit
class TestOPR:
    def test_renders_decisions_and_window_change(self):
        stub = _request_stub({"opr/year/2024": _OPR_2024, "opr/year/2025": _OPR_2025})
        with mock.patch.object(bnm, "_request", stub):
            out = bnm.get_macro_data("opr", "2025-12-31", look_back_days=365)
        assert "Overnight Policy Rate" in out
        assert "2.75" in out
        assert "2025-07-09" in out
        # Entered the window at 3.00 and ended at 2.75.
        assert "-0.25 pp" in out

    def test_no_decision_in_window_reports_unchanged_not_missing(self):
        """A stable OPR is 'unchanged', never 'no data' — see module docstring."""
        prior = {"data": [{"date": "2023-05-03", "new_opr_level": 3.00}]}
        with mock.patch.object(
            bnm, "_request", _request_stub({"opr/year/2023": prior}, default={"data": []})
        ):
            out = bnm.get_macro_data("opr", "2024-06-30", look_back_days=365)
        assert "unchanged" in out.lower()
        assert "3.00" in out
        assert "not missing data" in out
        assert "NO_DATA" not in out

    def test_excludes_decisions_after_curr_date(self):
        """Lookahead guard: a later decision must not leak into a past run."""
        stub = _request_stub({"opr/year/2024": _OPR_2024, "opr/year/2025": _OPR_2025})
        with mock.patch.object(bnm, "_request", stub):
            out = bnm.get_macro_data("opr", "2025-08-01", look_back_days=365)
        assert "2025-07-09" in out
        assert "2025-11-06" not in out

    def test_tolerates_alternate_level_field_name(self):
        payload = {"data": [{"date": "2025-07-09", "opr_level": 2.75}]}
        with mock.patch.object(
            bnm, "_request", _request_stub({"opr/year/2025": payload}, default={"data": []})
        ):
            out = bnm.get_macro_data("opr", "2025-12-31", look_back_days=365)
        assert "2.75" in out

    def test_skips_rows_missing_a_level(self):
        payload = {"data": [{"date": "2025-07-09"}, {"date": "2025-08-09", "new_opr_level": 2.50}]}
        with mock.patch.object(
            bnm, "_request", _request_stub({"opr/year/2025": payload}, default={"data": []})
        ):
            out = bnm.get_macro_data("opr", "2025-12-31", look_back_days=365)
        assert "2.50" in out
        assert "2025-07-09" not in out


@pytest.mark.unit
class TestUsdMyr:
    def test_renders_rate_and_direction(self):
        with mock.patch.object(bnm, "_request", _request_stub({"kl-usd": _FX})):
            out = bnm.get_macro_data("usd_myr", "2025-09-30", look_back_days=45)
        assert "4.2300" in out
        assert "weaker" in out  # USD/MYR rose

    def test_stronger_ringgit_when_rate_falls(self):
        falling = {"data": [{"date": "2025-09-01", "rate": 4.30}, {"date": "2025-09-02", "rate": 4.20}]}
        with mock.patch.object(bnm, "_request", _request_stub({"kl-usd": falling})):
            out = bnm.get_macro_data("usd_myr", "2025-09-30", look_back_days=45)
        assert "stronger" in out

    def test_excludes_rates_after_curr_date(self):
        with mock.patch.object(bnm, "_request", _request_stub({"kl-usd": _FX})):
            out = bnm.get_macro_data("usd_myr", "2025-09-01", look_back_days=30)
        assert "2025-09-01" in out
        assert "4.2300" not in out

    def test_month_fanout_is_capped(self):
        calls = []

        def _counting(path):
            calls.append(path)
            return _FX

        with mock.patch.object(bnm, "_request", _counting):
            bnm.get_macro_data("usd_myr", "2025-09-30", look_back_days=365 * 5)
        assert len(calls) == bnm._MAX_FX_MONTHS


@pytest.mark.unit
class TestRequestHandling:
    def test_404_is_an_empty_period_not_an_error(self):
        resp = mock.Mock(status_code=404)
        with mock.patch.object(bnm.requests, "get", return_value=resp):
            assert bnm._request("opr/year/2099") == {}

    def test_server_error_raises_vendor_error(self):
        resp = mock.Mock(status_code=500)
        with (
            mock.patch.object(bnm.requests, "get", return_value=resp),
            pytest.raises(bnm.BnmUnavailableError),
        ):
            bnm._request("opr/year/2025")

    def test_object_data_is_normalized_to_a_list(self):
        assert bnm._rows({"data": {"date": "2025-01-01"}}) == [{"date": "2025-01-01"}]
        assert bnm._rows({"data": None}) == []


@pytest.mark.unit
class TestRouting:
    def test_bnm_is_registered_for_macro(self):
        assert "bnm" in interface.VENDOR_METHODS["get_macro_indicators"]
        assert "bnm" in interface.VENDOR_LIST

    def test_us_indicator_falls_through_to_fred(self):
        """The default 'bnm,fred' chain must still serve US series."""
        config = copy.deepcopy(default_config.DEFAULT_CONFIG)
        config["data_vendors"]["macro_data"] = "bnm,fred"
        set_config(config)
        fred_impl = mock.Mock(return_value="FRED-REPORT")
        with mock.patch.dict(
            interface.VENDOR_METHODS["get_macro_indicators"], {"fred": fred_impl}
        ):
            out = interface.route_to_vendor(
                "get_macro_indicators", "fed_funds_rate", "2025-09-16", None
            )
        assert out == "FRED-REPORT"

    def test_my_indicator_is_served_by_bnm(self):
        config = copy.deepcopy(default_config.DEFAULT_CONFIG)
        config["data_vendors"]["macro_data"] = "bnm,fred"
        set_config(config)
        stub = _request_stub({"opr/year/2024": _OPR_2024, "opr/year/2025": _OPR_2025})
        with mock.patch.object(bnm, "_request", stub):
            out = interface.route_to_vendor(
                "get_macro_indicators", "opr", "2025-12-31", 365
            )
        assert "Overnight Policy Rate" in out

    def test_default_config_puts_bnm_ahead_of_fred(self):
        assert default_config.DEFAULT_CONFIG["data_vendors"]["macro_data"] == "bnm,fred"


@pytest.mark.unit
class TestFxDeduplication:
    """The FX series is fetched one month per request; overlapping boundary
    days must not be counted twice."""

    def test_dates_repeated_across_months_are_deduped(self):
        overlap = {
            "data": [
                {"date": "2025-08-29", "rate": 4.20},
                {"date": "2025-09-01", "rate": 4.25},
            ]
        }
        # Same payload for every month request, as an overlapping API would.
        with mock.patch.object(bnm, "_request", lambda path: overlap):
            points, _ = bnm._fetch_usd_myr("2025-08-01", "2025-09-30")
        assert [d for d, _ in points] == ["2025-08-29", "2025-09-01"]

    def test_deduped_series_does_not_distort_the_change(self):
        overlap = {
            "data": [
                {"date": "2025-08-29", "rate": 4.20},
                {"date": "2025-09-01", "rate": 4.25},
            ]
        }
        with mock.patch.object(bnm, "_request", lambda path: overlap):
            out = bnm.get_macro_data("usd_myr", "2025-09-30", look_back_days=60)
        assert out.count("| 2025-08-29 |") == 1
        assert "+0.0500" in out
