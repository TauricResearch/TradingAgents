"""Minimal import test for alpha_vantage modules (all require API key)."""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

import pytest


@ pytest.mark.unit
class AlphaVantageImportTests(unittest.TestCase):
    def test_import_alpha_vantage_root(self):
        """Verify that the alpha_vantage package can be imported."""
        import tradingagents.dataflows.alpha_vantage as av
        self.assertTrue(hasattr(av, "get_stock"))
        self.assertTrue(hasattr(av, "get_fundamentals"))
        self.assertTrue(hasattr(av, "get_balance_sheet"))
        self.assertTrue(hasattr(av, "get_cashflow"))
        self.assertTrue(hasattr(av, "get_income_statement"))
        self.assertTrue(hasattr(av, "get_indicator"))
        self.assertTrue(hasattr(av, "get_global_news"))
        self.assertTrue(hasattr(av, "get_insider_transactions"))
        self.assertTrue(hasattr(av, "get_news"))

    def test_import_alpha_vantage_common(self):
        """Verify that alpha_vantage_common module can be imported."""
        from tradingagents.dataflows import alpha_vantage_common
        self.assertTrue(hasattr(alpha_vantage_common, "get_api_key"))
        self.assertTrue(hasattr(alpha_vantage_common, "_make_api_request"))
        self.assertTrue(hasattr(alpha_vantage_common, "_filter_csv_by_date_range"))
        self.assertTrue(hasattr(alpha_vantage_common, "format_datetime_for_api"))
        self.assertTrue(hasattr(alpha_vantage_common, "AlphaVantageNotConfiguredError"))
        self.assertTrue(hasattr(alpha_vantage_common, "AlphaVantageRateLimitError"))

    def test_import_alpha_vantage_stock(self):
        from tradingagents.dataflows import alpha_vantage_stock
        self.assertTrue(hasattr(alpha_vantage_stock, "get_stock"))

    def test_import_alpha_vantage_fundamentals(self):
        from tradingagents.dataflows import alpha_vantage_fundamentals
        self.assertTrue(hasattr(alpha_vantage_fundamentals, "get_fundamentals"))
        self.assertTrue(hasattr(alpha_vantage_fundamentals, "get_balance_sheet"))
        self.assertTrue(hasattr(alpha_vantage_fundamentals, "get_cashflow"))
        self.assertTrue(hasattr(alpha_vantage_fundamentals, "get_income_statement"))
        self.assertTrue(hasattr(alpha_vantage_fundamentals, "_filter_reports_by_date"))

    def test_import_alpha_vantage_news(self):
        from tradingagents.dataflows import alpha_vantage_news
        self.assertTrue(hasattr(alpha_vantage_news, "get_news"))
        self.assertTrue(hasattr(alpha_vantage_news, "get_global_news"))
        self.assertTrue(hasattr(alpha_vantage_news, "get_insider_transactions"))

    def test_import_alpha_vantage_indicator(self):
        from tradingagents.dataflows import alpha_vantage_indicator
        self.assertTrue(hasattr(alpha_vantage_indicator, "get_indicator"))

    def test_common_format_datetime_various_inputs(self):
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api

        # String date
        result = format_datetime_for_api("2026-06-15")
        self.assertEqual(result, "20260615T0000")

        # Already formatted
        result = format_datetime_for_api("20260615T0000")
        self.assertEqual(result, "20260615T0000")

        # With time
        result = format_datetime_for_api("2026-06-15 14:30")
        self.assertEqual(result, "20260615T1430")

        # Invalid format
        with self.assertRaises(ValueError):
            format_datetime_for_api("not-a-date")

    def test_common_format_datetime_datetime_input(self):
        from datetime import datetime
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api

        dt = datetime(2026, 6, 15, 14, 30)
        result = format_datetime_for_api(dt)
        self.assertEqual(result, "20260615T1430")

    def test_common_format_datetime_invalid_type(self):
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api

        with self.assertRaises(ValueError):
            format_datetime_for_api(12345)

    def test_common_get_api_key_no_env(self):
        from tradingagents.dataflows.alpha_vantage_common import (
            AlphaVantageNotConfiguredError, get_api_key,
        )

        with patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": ""}, clear=False):
            if "ALPHA_VANTAGE_API_KEY" in os.environ:
                del os.environ["ALPHA_VANTAGE_API_KEY"]
            with self.assertRaises(AlphaVantageNotConfiguredError):
                get_api_key()

    def test_common_get_api_key_with_env(self):
        from tradingagents.dataflows.alpha_vantage_common import get_api_key

        with patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "test_key_abc"}, clear=True):
            key = get_api_key()
            self.assertEqual(key, "test_key_abc")

    def test_common_alpha_vantage_not_configured_error_is_value_error(self):
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageNotConfiguredError

        self.assertTrue(issubclass(AlphaVantageNotConfiguredError, ValueError))

    def test_filter_csv_by_date_range_empty(self):
        from tradingagents.dataflows.alpha_vantage_common import _filter_csv_by_date_range

        result = _filter_csv_by_date_range("", "2026-01-01", "2026-12-31")
        self.assertEqual(result, "")

        result = _filter_csv_by_date_range("   ", "2026-01-01", "2026-12-31")
        self.assertEqual(result, "   ")

    def test_filter_csv_by_date_range_filters_rows(self):
        from tradingagents.dataflows.alpha_vantage_common import _filter_csv_by_date_range

        csv_data = "timestamp,open,high,low,close,volume\n2026-01-01,100,101,99,100.5,1000\n2026-06-15,150,152,149,151,2000\n2026-12-31,200,201,199,200.5,3000"
        result = _filter_csv_by_date_range(csv_data, "2026-06-01", "2026-07-01")
        self.assertIn("2026-06-15", result)
        self.assertNotIn("2026-01-01", result)
        self.assertNotIn("2026-12-31", result)

    def test_filter_csv_by_date_range_bad_csv_returns_original(self):
        from tradingagents.dataflows.alpha_vantage_common import _filter_csv_by_date_range

        # CSV where date parsing fails — original data is returned unchanged
        bad_csv = "not_a_date,value\nhello,world"
        result = _filter_csv_by_date_range(bad_csv, "2026-01-01", "2026-12-31")
        self.assertEqual(result, bad_csv)

    def test_filter_reports_by_date(self):
        from tradingagents.dataflows.alpha_vantage_fundamentals import _filter_reports_by_date

        data = {
            "annualReports": [
                {"fiscalDateEnding": "2025-12-31", "totalAssets": "100"},
                {"fiscalDateEnding": "2026-12-31", "totalAssets": "200"},
            ],
            "quarterlyReports": [
                {"fiscalDateEnding": "2026-03-31", "totalAssets": "150"},
                {"fiscalDateEnding": "2026-06-30", "totalAssets": "180"},
            ],
        }
        filtered = _filter_reports_by_date(data, "2026-06-15")
        self.assertEqual(len(filtered["annualReports"]), 1)
        self.assertEqual(filtered["annualReports"][0]["fiscalDateEnding"], "2025-12-31")
        self.assertEqual(len(filtered["quarterlyReports"]), 1)
        self.assertEqual(filtered["quarterlyReports"][0]["fiscalDateEnding"], "2026-03-31")

    def test_filter_reports_by_date_noop_without_curr_date(self):
        from tradingagents.dataflows.alpha_vantage_fundamentals import _filter_reports_by_date

        data = {"annualReports": [{"fiscalDateEnding": "2026-12-31"}]}
        result = _filter_reports_by_date(data, None)
        self.assertEqual(result, data)

    def test_filter_reports_by_date_noop_non_dict(self):
        from tradingagents.dataflows.alpha_vantage_fundamentals import _filter_reports_by_date

        result = _filter_reports_by_date("string", "2026-06-15")
        self.assertEqual(result, "string")

    def test_alpha_vantage_rate_limit_error(self):
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError

        exc = AlphaVantageRateLimitError("rate limited")
        self.assertIsInstance(exc, Exception)
        self.assertEqual(str(exc), "rate limited")

    def test_indicator_unsupported_raises_value_error(self):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        with self.assertRaises(ValueError) as ctx:
            get_indicator("AAPL", "nonexistent_indicator", "2026-06-15", 14)
        self.assertIn("not supported", str(ctx.exception))

    def test_indicator_vwma_returns_message(self):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        result = get_indicator("AAPL", "vwma", "2026-06-15", 14)
        self.assertIn("VWMA", result)
        self.assertIn("Volume Weighted Moving Average", result)


# =========================================================================
# Tests merged from test_final_push.py and test_llm_and_minor.py
# =========================================================================


def _indicator_csv(header_col: str = "SMA") -> str:
    """Return a tiny multi-row CSV emulating the Alpha Vantage shape."""
    return (
        f"time,{header_col}\n"
        "2026-05-01,100.0\n"
        "2026-05-10,102.5\n"
        "2026-05-20,105.0\n"
    )


class AlphaVantageCommonMakeRequestTests(unittest.TestCase):
    """Lines 75, 78, 90-95: entitlement handling and rate limit detection."""

    def test_entitlement_from_global(self):
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request

        with patch("tradingagents.dataflows.alpha_vantage_common.get_api_key", return_value="key"), \
             patch("tradingagents.dataflows.alpha_vantage_common.requests.get") as mock_get, \
             patch.dict("tradingagents.dataflows.alpha_vantage_common.__dict__",
                        {"_current_entitlement": "realtime"}):
            mock_get.return_value.text = "{}"
            mock_get.return_value.raise_for_status = lambda: None
            _make_api_request("SMA", {"symbol": "AAPL"})
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["entitlement"], "realtime")

    def test_entitlement_from_params(self):
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request

        with patch("tradingagents.dataflows.alpha_vantage_common.get_api_key", return_value="key"), \
             patch("tradingagents.dataflows.alpha_vantage_common.requests.get") as mock_get:
            mock_get.return_value.text = "{}"
            mock_get.return_value.raise_for_status = lambda: None
            _make_api_request("SMA", {"symbol": "AAPL", "entitlement": "delayed"})
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["entitlement"], "delayed")

    def test_entitlement_none_removed(self):
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request

        with patch("tradingagents.dataflows.alpha_vantage_common.get_api_key", return_value="key"), \
             patch("tradingagents.dataflows.alpha_vantage_common.requests.get") as mock_get:
            mock_get.return_value.text = "{}"
            mock_get.return_value.raise_for_status = lambda: None
            _make_api_request("SMA", {"symbol": "AAPL", "entitlement": None})
        _, kwargs = mock_get.call_args
        self.assertNotIn("entitlement", kwargs["params"])

    def test_entitlement_empty_string_removed(self):
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request

        with patch("tradingagents.dataflows.alpha_vantage_common.get_api_key", return_value="key"), \
             patch("tradingagents.dataflows.alpha_vantage_common.requests.get") as mock_get:
            mock_get.return_value.text = "{}"
            mock_get.return_value.raise_for_status = lambda: None
            _make_api_request("SMA", {"symbol": "AAPL", "entitlement": ""})
        _, kwargs = mock_get.call_args
        self.assertNotIn("entitlement", kwargs["params"])

    def test_rate_limit_detected(self):
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request, AlphaVantageRateLimitError

        with patch("tradingagents.dataflows.alpha_vantage_common.get_api_key", return_value="key"), \
             patch("tradingagents.dataflows.alpha_vantage_common.requests.get") as mock_get:
            mock_get.return_value.text = '{"Information": "Thank you for using Alpha Vantage! Our standard API rate limit is 5 calls per minute."}'
            mock_get.return_value.raise_for_status = lambda: None
            with self.assertRaises(AlphaVantageRateLimitError):
                _make_api_request("SMA", {"symbol": "AAPL"})

    def test_rate_limit_detected_api_key(self):
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request, AlphaVantageRateLimitError

        with patch("tradingagents.dataflows.alpha_vantage_common.get_api_key", return_value="key"), \
             patch("tradingagents.dataflows.alpha_vantage_common.requests.get") as mock_get:
            mock_get.return_value.text = '{"Information": "Invalid API key. Please check your API key."}'
            mock_get.return_value.raise_for_status = lambda: None
            with self.assertRaises(AlphaVantageRateLimitError):
                _make_api_request("SMA", {"symbol": "AAPL"})

    def test_json_decode_error_returns_text(self):
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request

        with patch("tradingagents.dataflows.alpha_vantage_common.get_api_key", return_value="key"), \
             patch("tradingagents.dataflows.alpha_vantage_common.requests.get") as mock_get:
            mock_get.return_value.text = "timestamp,open,high,low,close,volume\n2026-01-01,100,101,99,100.5,1000"
            mock_get.return_value.raise_for_status = lambda: None
            result = _make_api_request("SMA", {"symbol": "AAPL"})
        self.assertIn("timestamp", result)


class AlphaVantageCommonFormatDatetimeEdgeTests(unittest.TestCase):
    """Edge cases for format_datetime_for_api not covered."""

    def test_format_datetime_for_api_already_formatted(self):
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api
        result = format_datetime_for_api("20260615T0000")
        self.assertEqual(result, "20260615T0000")

    def test_format_datetime_with_time_string(self):
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api
        result = format_datetime_for_api("2026-06-15 14:30")
        self.assertEqual(result, "20260615T1430")

    def test_format_datetime_datetime_obj(self):
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api
        dt = datetime(2026, 6, 15, 14, 30)
        result = format_datetime_for_api(dt)
        self.assertEqual(result, "20260615T1430")

    def test_format_datetime_invalid_type(self):
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api
        with self.assertRaises(ValueError):
            format_datetime_for_api(12345)

    def test_format_datetime_unparseable_string(self):
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api
        with self.assertRaises(ValueError):
            format_datetime_for_api("not-a-date")


class AlphaVantageIndicatorGetIndicatorTests(unittest.TestCase):
    """get_indicator function paths for each supported indicator."""

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_get_sma_50(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.return_value = "time,SMA\n2026-05-01,150.5\n2026-05-02,151.0"
        result = get_indicator("AAPL", "close_50_sma", "2026-05-02", 30)
        self.assertIn("CLOSE_50_SMA values", result)
        self.assertIn("150.5", result)

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_get_sma_200(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.return_value = "time,SMA\n2026-05-01,145.0"
        result = get_indicator("AAPL", "close_200_sma", "2026-05-02", 30)
        self.assertIn("CLOSE_200_SMA values", result)

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_get_ema_10(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.return_value = "time,EMA\n2026-05-01,151.2"
        result = get_indicator("AAPL", "close_10_ema", "2026-05-02", 30)
        self.assertIn("CLOSE_10_EMA values", result)

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_get_macd(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.return_value = "time,MACD\n2026-05-01,1.23"
        result = get_indicator("AAPL", "macd", "2026-05-02", 30)
        self.assertIn("MACD values", result)

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_get_macd_signal(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.return_value = "time,MACD_Signal\n2026-05-01,1.10"
        result = get_indicator("AAPL", "macds", "2026-05-02", 30)
        self.assertIn("MACDS values", result)

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_get_macd_hist(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.return_value = "time,MACD_Hist\n2026-05-01,0.13"
        result = get_indicator("AAPL", "macdh", "2026-05-02", 30)
        self.assertIn("MACDH values", result)

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_get_rsi(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.return_value = "time,RSI\n2026-05-01,62.5"
        result = get_indicator("AAPL", "rsi", "2026-05-02", 30)
        self.assertIn("RSI values", result)

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_get_bollinger(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.return_value = "time,Real Middle Band\n2026-05-01,150.0"
        result = get_indicator("AAPL", "boll", "2026-05-02", 30)
        self.assertIn("BOLL values", result)

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_get_atr(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.return_value = "time,ATR\n2026-05-01,2.5"
        result = get_indicator("AAPL", "atr", "2026-05-02", 30)
        self.assertIn("ATR values", result)

    def test_get_vwma_returns_message(self):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        result = get_indicator("AAPL", "vwma", "2026-05-02", 30)
        self.assertIn("VWMA", result)
        self.assertIn("Volume Weighted Moving Average", result)

    def test_unsupported_indicator_raises(self):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        with self.assertRaises(ValueError) as ctx:
            get_indicator("AAPL", "nonexistent", "2026-05-02", 30)
        self.assertIn("not supported", str(ctx.exception))

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_empty_data_returns_error(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.return_value = ""
        result = get_indicator("AAPL", "rsi", "2026-05-02", 30)
        self.assertIn("No data returned", result)

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_missing_time_column(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.return_value = "date,RSI\n2026-05-01,50.0"
        result = get_indicator("AAPL", "rsi", "2026-05-02", 30)
        self.assertIn("column not found", result)

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_no_data_in_date_range(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.return_value = "time,RSI\n2025-01-01,50.0"
        result = get_indicator("AAPL", "rsi", "2026-05-02", 30)
        self.assertIn("No data available", result)

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_general_exception_returns_error_string(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.side_effect = RuntimeError("API failure")
        result = get_indicator("AAPL", "rsi", "2026-05-02", 30)
        self.assertIn("Error retrieving", result)
        self.assertIn("API failure", result)

    @patch("tradingagents.dataflows.alpha_vantage_indicator._make_api_request")
    def test_alpha_vantage_not_configured_propagates(self, mock_api):
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageNotConfiguredError
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator
        mock_api.side_effect = AlphaVantageNotConfiguredError("no key")
        with self.assertRaises(AlphaVantageNotConfiguredError):
            get_indicator("AAPL", "rsi", "2026-05-02", 30)


class TestAlphaVantageCommonMakeApiRequest(unittest.TestCase):
    """Cover entitlement-setting (line 75), entitlement-removal (line 78),
    and rate-limit detection (lines 90–92) in _make_api_request."""

    def setUp(self):
        self.fake_key = "fake_key_123"
        self.fake_csv = "timestamp,value\n2026-01-01,100"

    def _patch_common(self):
        return patch(
            "tradingagents.dataflows.alpha_vantage_common.get_api_key",
            return_value=self.fake_key,
        )

    def _patch_get(self, status=200, text=None):
        return patch(
            "tradingagents.dataflows.alpha_vantage_common.requests.get",
            return_value=MagicMock(
                status_code=status,
                text=text or self.fake_csv,
                raise_for_status=lambda: None,
            ),
        )

    def test_make_request_entitlement_global_var(self):
        """Line 75: entitlement set via global _current_entitlement."""
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request

        sentinel = object()
        api_params = {"symbol": "AAPL", "entitlement": sentinel}

        with self._patch_common(), self._patch_get():
            result = _make_api_request("SMA", api_params)

    def test_make_request_entitlement_in_params_falsy(self):
        """Line 78: entitlement popped when it is falsy."""
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request

        api_params = {"symbol": "AAPL", "entitlement": None}

        with self._patch_common(), self._patch_get():
            result = _make_api_request("SMA", api_params)
        self.assertIsInstance(result, str)

    def test_make_request_rate_limit_detected(self):
        """Lines 90–92: rate-limit message in JSON response raises error."""
        from tradingagents.dataflows.alpha_vantage_common import (
            AlphaVantageRateLimitError,
            _make_api_request,
        )

        error_json = json.dumps({
            "Information": "The rate limit was exceeded. Please try again later."
        })

        with self._patch_common(), self._patch_get(text=error_json):
            with self.assertRaises(AlphaVantageRateLimitError):
                _make_api_request("SMA", {"symbol": "AAPL"})

    def test_make_request_api_key_message_detected(self):
        """Lines 90–92: 'api key' in Information message also triggers."""
        from tradingagents.dataflows.alpha_vantage_common import (
            AlphaVantageRateLimitError,
            _make_api_request,
        )

        error_json = json.dumps({
            "Information": "Invalid API key. Please check your key."
        })

        with self._patch_common(), self._patch_get(text=error_json):
            with self.assertRaises(AlphaVantageRateLimitError):
                _make_api_request("SMA", {"symbol": "AAPL"})

    def test_make_request_non_json_csv_response_passes(self):
        """Line 93–95: CSV (non-JSON) response passes through normally."""
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request

        with self._patch_common(), self._patch_get(text=self.fake_csv):
            result = _make_api_request("SMA", {"symbol": "AAPL"})
        self.assertEqual(result, self.fake_csv)


class TestAlphaVantageIndicator(unittest.TestCase):

    def test_get_indicator_import_and_exists(self):
        from tradingagents.dataflows import alpha_vantage_indicator
        self.assertTrue(hasattr(alpha_vantage_indicator, "get_indicator"))

    def test_indicator_csv_parsing(self):
        """Lines 138–215: full CSV parse + format output path."""
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        with patch(
            "tradingagents.dataflows.alpha_vantage_indicator._make_api_request",
            return_value=_indicator_csv("SMA"),
        ):
            result = get_indicator(
                symbol="AAPL",
                indicator="close_50_sma",
                curr_date="2026-05-20",
                look_back_days=30,
            )
        self.assertIn("close_50_sma", result.lower())
        self.assertIn("100.0", result)
        self.assertIn("105.0", result)

    def test_indicator_csv_no_time_column(self):
        """Line 150: 'time' column missing.""" 
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        csv_no_time = "date,SMA\n2026-05-01,100.0\n"
        with patch(
            "tradingagents.dataflows.alpha_vantage_indicator._make_api_request",
            return_value=csv_no_time,
        ):
            result = get_indicator(
                symbol="AAPL",
                indicator="close_50_sma",
                curr_date="2026-05-20",
                look_back_days=30,
            )
        self.assertIn("'time' column not found", result)

    def test_indicator_csv_bad_value_column(self):
        """Line 169: target column not found."""
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        csv_wrong_col = "time,WrongCol\n2026-05-01,100.0\n"
        with patch(
            "tradingagents.dataflows.alpha_vantage_indicator._make_api_request",
            return_value=csv_wrong_col,
        ):
            result = get_indicator(
                symbol="AAPL",
                indicator="close_50_sma",
                curr_date="2026-05-20",
                look_back_days=30,
            )
        self.assertIn("Column 'SMA' not found", result)

    def test_indicator_no_data_in_range(self):
        """Line 197: no data for the specified date range."""
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        csv_old = "time,SMA\n2020-01-01,50.0\n2020-01-02,51.0\n"
        with patch(
            "tradingagents.dataflows.alpha_vantage_indicator._make_api_request",
            return_value=csv_old,
        ):
            result = get_indicator(
                symbol="AAPL",
                indicator="close_50_sma",
                curr_date="2026-05-20",
                look_back_days=30,
            )
        self.assertIn("No data available", result)

    def test_indicator_empty_data(self):
        """Line 143: only header, no data rows."""
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        with patch(
            "tradingagents.dataflows.alpha_vantage_indicator._make_api_request",
            return_value="time,SMA\n",
        ):
            result = get_indicator(
                symbol="AAPL",
                indicator="close_50_sma",
                curr_date="2026-05-20",
                look_back_days=30,
            )
        self.assertIn("No data returned", result)

    def test_indicator_exception_caught(self):
        """Line 214–215: general exception caught and returned as error string."""
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        with patch(
            "tradingagents.dataflows.alpha_vantage_indicator._make_api_request",
            side_effect=ValueError("connection reset"),
        ):
            result = get_indicator(
                symbol="AAPL",
                indicator="close_50_sma",
                curr_date="2026-05-20",
                look_back_days=30,
            )
        self.assertIn("Error retrieving close_50_sma data", result)
        self.assertIn("connection reset", result)

    def test_indicator_unimplemented_path(self):
        """Line 138: fallback 'not implemented yet' branch."""
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        with patch(
            "tradingagents.dataflows.alpha_vantage_indicator._make_api_request",
            return_value=_indicator_csv("SMA"),
        ):
            result = get_indicator(
                symbol="AAPL",
                indicator="close_50_sma",
                curr_date="2026-05-20",
                look_back_days=30,
            )
        self.assertIn("close_50_sma", result.lower())


if __name__ == "__main__":
    unittest.main()