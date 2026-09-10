"""FRED macro vendor: alias resolution, configuration errors, output formatting,
missing-value handling, lookahead-safe windowing, and router integration.

All API access is mocked, so these run without a network connection or a key.
"""
import copy
import unittest
from unittest import mock

import pytest
import requests

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import fred, interface
from tradingagents.dataflows.config import set_config

# A small, stable set of observations to format against.
_META = {
    "seriess": [
        {
            "title": "Unemployment Rate",
            "units_short": "%",
            "frequency": "Monthly",
            "seasonal_adjustment_short": "SA",
        }
    ]
}
_OBS = {
    "observations": [
        {"date": "2025-06-01", "value": "4.1"},
        {"date": "2025-07-01", "value": "4.3"},
        {"date": "2025-08-01", "value": "."},   # missing -> skipped
        {"date": "2025-09-01", "value": "4.4"},
    ]
}


def _request_stub(meta=_META, obs=_OBS):
    """Build a _request replacement that dispatches on the endpoint path."""
    def _impl(path, params):
        if path == "series":
            return meta
        if path == "series/observations":
            return obs
        raise AssertionError(f"unexpected FRED path: {path}")
    return _impl


@pytest.mark.unit
class FredResolutionTests(unittest.TestCase):
    def test_alias_maps_to_series_id(self):
        self.assertEqual(fred._resolve_series_id("cpi"), "CPIAUCSL")
        self.assertEqual(fred._resolve_series_id("unemployment"), "UNRATE")

    def test_alias_is_case_and_separator_insensitive(self):
        self.assertEqual(fred._resolve_series_id("Fed Funds Rate"), "FEDFUNDS")
        self.assertEqual(fred._resolve_series_id("10y-treasury"), "DGS10")

    def test_unknown_alias_is_treated_as_raw_series_id(self):
        # Power users can pass any FRED series ID; we uppercase by convention.
        self.assertEqual(fred._resolve_series_id("dgs30"), "DGS30")
        self.assertEqual(fred._resolve_series_id("MyCustomSeries"), "MYCUSTOMSERIES")

    def test_descriptive_phrase_is_rejected(self):
        # An LLM phrase (spaces / too long) is not a series ID — reject up front
        # with guidance rather than 400ing the API.
        for bad in ("bank of japan rate", "the unemployment number", "X" * 31):
            with self.assertRaises(ValueError):
                fred._resolve_series_id(bad)

    def test_get_macro_data_returns_guidance_on_bad_indicator(self):
        # Invalid indicator -> actionable message, not a crash (no API call).
        out = fred.get_macro_data("bank of japan rate", "2026-01-01")
        self.assertIn("FRED", out)
        self.assertIn("not a known macro alias", out)


@pytest.mark.unit
class FredConfigTests(unittest.TestCase):
    def test_missing_key_raises_not_configured(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
                self.assertRaises(fred.FredNotConfiguredError):
            fred.get_api_key()

    def test_not_configured_is_a_value_error(self):
        # Routing relies on this subclassing for "vendor unavailable" handling.
        self.assertTrue(issubclass(fred.FredNotConfiguredError, ValueError))


@pytest.mark.unit
class FredFormattingTests(unittest.TestCase):
    def test_report_has_header_latest_change_and_table(self):
        with mock.patch.object(fred, "_request", side_effect=_request_stub()):
            out = fred.get_macro_data("unemployment", "2025-09-30", 365)
        self.assertIn("## FRED: Unemployment Rate (UNRATE)", out)
        self.assertIn("Units: %", out)
        self.assertIn("Frequency: Monthly (SA)", out)
        self.assertIn("**Latest:** 4.4 (2025-09-01)", out)
        # change over the window: 4.4 - 4.1 = +0.30
        self.assertIn("+0.30", out)
        self.assertIn("| 2025-06-01 | 4.1 |", out)

    def test_missing_value_is_skipped(self):
        with mock.patch.object(fred, "_request", side_effect=_request_stub()):
            out = fred.get_macro_data("unemployment", "2025-09-30", 365)
        # the "." observation must not appear as a row
        self.assertNotIn("2025-08-01", out)

    def test_empty_window_reports_no_observations(self):
        empty = {"observations": []}
        with mock.patch.object(fred, "_request", side_effect=_request_stub(obs=empty)):
            out = fred.get_macro_data("unemployment", "2025-09-30", 30)
        self.assertIn("No observations", out)

    def test_unknown_series_returns_not_found_message(self):
        # A well-formed but unknown series ID returns guidance, not a crash, so
        # the run is not aborted over an optional macro lookup.
        no_series = {"seriess": []}
        with mock.patch.object(fred, "_request", side_effect=_request_stub(meta=no_series)):
            out = fred.get_macro_data("totally_unknown_xyz", "2025-09-30", 30)
        self.assertIn("not found", out)

    def test_long_series_is_truncated_but_change_uses_full_range(self):
        # Build > MAX_ROWS observations deterministically.
        obs = {
            "observations": [
                {"date": f"2025-01-{(i % 28) + 1:02d}", "value": str(i)}
                for i in range(fred.MAX_ROWS + 10)
            ]
        }
        with mock.patch.object(fred, "_request", side_effect=_request_stub(obs=obs)):
            out = fred.get_macro_data("unemployment", "2025-12-31", 365)
        self.assertIn(f"most recent {fred.MAX_ROWS}", out)
        # change-over-window must reference the true first (0) and last value
        self.assertIn("from 0 ", out)
        body_rows = [ln for ln in out.splitlines() if ln.startswith("| 2025")]
        self.assertEqual(len(body_rows), fred.MAX_ROWS)

    def test_window_is_lookahead_safe(self):
        # observation_end must equal curr_date so a past date never pulls future data.
        captured = {}

        def _capture(path, params):
            captured[path] = params
            return _META if path == "series" else _OBS

        with mock.patch.object(fred, "_request", side_effect=_capture):
            fred.get_macro_data("unemployment", "2025-09-30", 90)
        obs_params = captured["series/observations"]
        self.assertEqual(obs_params["observation_end"], "2025-09-30")
        self.assertEqual(obs_params["observation_start"], "2025-07-02")  # 90d back

    def test_requests_pin_the_data_vintage(self):
        # #1275: both the metadata and observations requests must pin the vintage
        # to curr_date (clamped to FRED's today), or FRED serves the latest
        # revision and revision-prone series leak future information. A past
        # curr_date sits below FRED's today, so it pins through unchanged.
        captured = {}

        def _capture(path, params):
            captured[path] = params
            return _META if path == "series" else _OBS

        with mock.patch.object(fred, "_fred_today", return_value="2026-01-01"), \
                mock.patch.object(fred, "_request", side_effect=_capture):
            fred.get_macro_data("cpi", "2025-09-30", 90)

        for path in ("series", "series/observations"):
            self.assertEqual(captured[path]["realtime_start"], "2025-09-30", path)
            self.assertEqual(captured[path]["realtime_end"], "2025-09-30", path)

    def test_future_curr_date_clamps_vintage_to_fred_today(self):
        # #1275 regression: on a live run curr_date is the caller's LOCAL date,
        # which can be a day ahead of FRED's US-Central clock. Pinning the vintage
        # to that future date 400s, and the routing layer then drops macro data
        # silently. The pin must clamp to FRED's today; the observation window
        # (future bars can't exist yet) stays at curr_date.
        captured = {}

        def _capture(path, params):
            captured[path] = params
            return _META if path == "series" else _OBS

        with mock.patch.object(fred, "_fred_today", return_value="2026-08-31"), \
                mock.patch.object(fred, "_request", side_effect=_capture):
            fred.get_macro_data("cpi", "2026-09-01", 90)  # local a day ahead of Chicago

        for path in ("series", "series/observations"):
            self.assertEqual(captured[path]["realtime_start"], "2026-08-31", path)
            self.assertEqual(captured[path]["realtime_end"], "2026-08-31", path)
        # the observation window still tracks curr_date, not the clamped vintage
        self.assertEqual(captured["series/observations"]["observation_end"], "2026-09-01")


@pytest.mark.unit
class FredKeyRedactionTests(unittest.TestCase):
    """The API key travels as a query parameter, so it must not reach an error string.

    ``requests`` builds its HTTPError message from the full URL, which carries
    ``api_key=...``. Anything that catches and logs that error — a retry wrapper,
    a caller's ``logger.warning``, an uncaught traceback in CI output — writes the
    key where it does not belong.
    """

    def test_redact_replaces_the_key_but_keeps_the_rest(self):
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            "?series_id=DGS10&api_key=abcdef0123456789abcdef0123456789&file_type=json"
        )
        redacted = fred.redact(url)
        self.assertNotIn("abcdef0123456789abcdef0123456789", redacted)
        self.assertIn("api_key=REDACTED", redacted)
        self.assertIn("series_id=DGS10", redacted)
        self.assertIn("file_type=json", redacted)

    def test_redact_leaves_text_without_a_key_alone(self):
        self.assertEqual(fred.redact("no key here"), "no key here")

    def test_http_error_message_carries_no_key(self):
        """A 500 must surface as an HTTPError whose message is scrubbed."""
        response = mock.Mock(status_code=500)
        response.raise_for_status.side_effect = requests.HTTPError(
            "500 Server Error for url: https://api.stlouisfed.org/fred/series"
            "?series_id=DGS10&api_key=abcdef0123456789abcdef0123456789"
        )
        with mock.patch.dict("os.environ", {"FRED_API_KEY": "abcdef0123456789abcdef0123456789"}):
            with mock.patch("requests.get", return_value=response):
                with self.assertRaises(requests.HTTPError) as caught:
                    fred._request("series", {"series_id": "DGS10"})
        self.assertNotIn("abcdef0123456789abcdef0123456789", str(caught.exception))
        self.assertIn("api_key=REDACTED", str(caught.exception))

    def test_http_error_keeps_its_class_and_response(self):
        """Callers matching on HTTPError, or reading the status code, still work."""
        response = mock.Mock(status_code=503)
        response.raise_for_status.side_effect = requests.HTTPError("503 for url: ?api_key=k")
        with mock.patch.dict("os.environ", {"FRED_API_KEY": "k" * 32}):
            with mock.patch("requests.get", return_value=response):
                with self.assertRaises(requests.HTTPError) as caught:
                    fred._request("series", {"series_id": "DGS10"})
        self.assertIs(caught.exception.response, response)
        self.assertEqual(caught.exception.response.status_code, 503)

    def test_bad_request_body_is_redacted_too(self):
        """FRED's own 400 body can quote the request; scrub that path as well."""
        response = mock.Mock(status_code=400)
        response.json.return_value = {
            "error_message": "Bad request: api_key=abcdef0123456789abcdef0123456789"
        }
        with mock.patch.dict("os.environ", {"FRED_API_KEY": "abcdef0123456789abcdef0123456789"}):
            with mock.patch("requests.get", return_value=response):
                with self.assertRaises(ValueError) as caught:
                    fred._request("series", {"series_id": "NOPE"})
        self.assertNotIn("abcdef0123456789abcdef0123456789", str(caught.exception))


class FredRoutingTests(unittest.TestCase):
    def setUp(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def tearDown(self):
        config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)

    def test_macro_category_routes_to_fred(self):
        self.assertEqual(
            interface.get_category_for_method("get_macro_indicators"), "macro_data"
        )
        set_config({"data_vendors": {"macro_data": "fred"}})
        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_macro_indicators": {"fred": lambda *a, **k: "MACRO_OK"}},
            clear=False,
        ):
            out = interface.route_to_vendor("get_macro_indicators", "cpi", "2026-06-01", 365)
        self.assertEqual(out, "MACRO_OK")

    def test_not_configured_degrades_gracefully(self):
        # macro_data is optional: with only fred and no key, the router degrades
        # to a sentinel instead of aborting the run — a missing optional key must
        # not crash an analysis.
        set_config({"data_vendors": {"macro_data": "fred"}})

        def _unconfigured(*a, **k):
            raise fred.FredNotConfiguredError("FRED_API_KEY not set")

        with mock.patch.dict(
            interface.VENDOR_METHODS,
            {"get_macro_indicators": {"fred": _unconfigured}},
            clear=False,
        ):
            out = interface.route_to_vendor("get_macro_indicators", "cpi", "2026-06-01", 365)
        self.assertIn("DATA_UNAVAILABLE", out)


if __name__ == "__main__":
    unittest.main()
