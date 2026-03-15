"""Integration tests for the Alpha Vantage data layer.

All HTTP requests are mocked so these tests run offline and without API-key or
rate-limit concerns.  The mocks reproduce realistic Alpha Vantage response shapes
so that the code-under-test exercises every significant branch.
"""

import json
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CSV_DAILY_ADJUSTED = (
    "timestamp,open,high,low,close,adjusted_close,volume,dividend_amount,split_coefficient\n"
    "2024-01-05,185.00,187.50,184.20,186.00,186.00,50000000,0.0000,1.0\n"
    "2024-01-04,183.00,186.00,182.50,185.00,185.00,45000000,0.0000,1.0\n"
    "2024-01-03,181.00,184.00,180.00,183.00,183.00,48000000,0.0000,1.0\n"
)

RATE_LIMIT_JSON = json.dumps({
    "Information": (
        "Thank you for using Alpha Vantage! Our standard API rate limit is 25 requests "
        "per day. Please subscribe to any of the premium plans at "
        "https://www.alphavantage.co/premium/ to instantly remove all daily rate limits."
    )
})

INVALID_KEY_JSON = json.dumps({
    "Information": "Invalid API key. Please claim your free API key at https://www.alphavantage.co/support/"
})

CSV_SMA = (
    "time,SMA\n"
    "2024-01-05,182.50\n"
    "2024-01-04,181.00\n"
    "2024-01-03,179.50\n"
)

CSV_RSI = (
    "time,RSI\n"
    "2024-01-05,55.30\n"
    "2024-01-04,53.10\n"
    "2024-01-03,51.90\n"
)

OVERVIEW_JSON = json.dumps({
    "Symbol": "AAPL",
    "Name": "Apple Inc",
    "Sector": "TECHNOLOGY",
    "MarketCapitalization": "3000000000000",
    "PERatio": "30.5",
    "Beta": "1.2",
})


def _mock_response(text: str, status_code: int = 200):
    """Return a mock requests.Response with the given text body."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# AlphaVantageRateLimitError
# ---------------------------------------------------------------------------

class TestAlphaVantageRateLimitError:
    """Tests for the custom AlphaVantageRateLimitError exception class."""

    def test_is_exception_subclass(self):
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError

        assert issubclass(AlphaVantageRateLimitError, Exception)

    def test_can_be_raised_and_caught(self):
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError

        with pytest.raises(AlphaVantageRateLimitError, match="rate limit"):
            raise AlphaVantageRateLimitError("rate limit exceeded")


# ---------------------------------------------------------------------------
# _make_api_request
# ---------------------------------------------------------------------------

class TestMakeApiRequest:
    """Tests for the internal _make_api_request helper."""

    def test_returns_csv_text_on_success(self):
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(CSV_DAILY_ADJUSTED)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = _make_api_request("TIME_SERIES_DAILY_ADJUSTED",
                                           {"symbol": "AAPL", "datatype": "csv"})

        assert "timestamp" in result
        assert "186.00" in result

    def test_raises_rate_limit_error_on_information_field(self):
        from tradingagents.dataflows.alpha_vantage_common import (
            _make_api_request,
            AlphaVantageRateLimitError,
        )

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(RATE_LIMIT_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                with pytest.raises(AlphaVantageRateLimitError):
                    _make_api_request("TIME_SERIES_DAILY_ADJUSTED", {"symbol": "AAPL"})

    def test_raises_rate_limit_error_for_invalid_api_key(self):
        from tradingagents.dataflows.alpha_vantage_common import (
            _make_api_request,
            AlphaVantageRateLimitError,
        )

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(INVALID_KEY_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "invalid_key"}):
                with pytest.raises(AlphaVantageRateLimitError):
                    _make_api_request("OVERVIEW", {"symbol": "AAPL"})

    def test_missing_api_key_raises_value_error(self):
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request
        import os

        env = {k: v for k, v in os.environ.items() if k != "ALPHA_VANTAGE_API_KEY"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(ValueError, match="ALPHA_VANTAGE_API_KEY"):
                _make_api_request("OVERVIEW", {"symbol": "AAPL"})

    def test_network_timeout_propagates(self):
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   side_effect=TimeoutError("connection timed out")):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                with pytest.raises(TimeoutError):
                    _make_api_request("OVERVIEW", {"symbol": "AAPL"})

    def test_http_error_propagates_via_raise_for_status(self):
        """HTTP 4xx/5xx raises an exception via response.raise_for_status()."""
        import requests as _requests
        from tradingagents.dataflows.alpha_vantage_common import _make_api_request

        bad_resp = _mock_response("", status_code=403)
        bad_resp.raise_for_status.side_effect = _requests.HTTPError("403 Forbidden")

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=bad_resp):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                with pytest.raises(_requests.HTTPError):
                    _make_api_request("OVERVIEW", {"symbol": "AAPL"})


# ---------------------------------------------------------------------------
# _filter_csv_by_date_range
# ---------------------------------------------------------------------------

class TestFilterCsvByDateRange:
    """Tests for the _filter_csv_by_date_range helper."""

    def test_filters_rows_to_date_range(self):
        from tradingagents.dataflows.alpha_vantage_common import _filter_csv_by_date_range

        result = _filter_csv_by_date_range(CSV_DAILY_ADJUSTED, "2024-01-04", "2024-01-05")

        assert "2024-01-03" not in result
        assert "2024-01-04" in result
        assert "2024-01-05" in result

    def test_empty_input_returns_empty(self):
        from tradingagents.dataflows.alpha_vantage_common import _filter_csv_by_date_range

        assert _filter_csv_by_date_range("", "2024-01-01", "2024-01-31") == ""

    def test_whitespace_only_input_returns_as_is(self):
        from tradingagents.dataflows.alpha_vantage_common import _filter_csv_by_date_range

        result = _filter_csv_by_date_range("   ", "2024-01-01", "2024-01-31")
        assert result.strip() == ""

    def test_all_rows_outside_range_returns_header_only(self):
        from tradingagents.dataflows.alpha_vantage_common import _filter_csv_by_date_range

        result = _filter_csv_by_date_range(CSV_DAILY_ADJUSTED, "2023-01-01", "2023-12-31")
        lines = [l for l in result.strip().split("\n") if l]
        # Only header row should remain
        assert len(lines) == 1
        assert "timestamp" in lines[0]


# ---------------------------------------------------------------------------
# format_datetime_for_api
# ---------------------------------------------------------------------------

class TestFormatDatetimeForApi:
    """Tests for format_datetime_for_api."""

    def test_yyyy_mm_dd_is_converted(self):
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api

        result = format_datetime_for_api("2024-01-15")
        assert result == "20240115T0000"

    def test_already_formatted_string_is_returned_as_is(self):
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api

        result = format_datetime_for_api("20240115T1430")
        assert result == "20240115T1430"

    def test_datetime_object_is_converted(self):
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api
        from datetime import datetime

        dt = datetime(2024, 1, 15, 14, 30)
        result = format_datetime_for_api(dt)
        assert result == "20240115T1430"

    def test_unsupported_string_format_raises_value_error(self):
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api

        with pytest.raises(ValueError):
            format_datetime_for_api("15-01-2024")

    def test_unsupported_type_raises_value_error(self):
        from tradingagents.dataflows.alpha_vantage_common import format_datetime_for_api

        with pytest.raises(ValueError):
            format_datetime_for_api(20240115)


# ---------------------------------------------------------------------------
# get_stock (alpha_vantage_stock)
# ---------------------------------------------------------------------------

class TestAlphaVantageGetStock:
    """Tests for the Alpha Vantage get_stock function."""

    def test_returns_csv_for_recent_date_range(self):
        """Recent dates → compact outputsize; CSV data is filtered to range."""
        from tradingagents.dataflows.alpha_vantage_stock import get_stock

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(CSV_DAILY_ADJUSTED)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_stock("AAPL", "2024-01-01", "2024-01-05")

        assert isinstance(result, str)

    def test_uses_full_outputsize_for_old_start_date(self):
        """Old start date (>100 days ago) → outputsize=full is selected."""
        from tradingagents.dataflows.alpha_vantage_stock import get_stock

        captured_params = {}

        def capture_request(url, params):
            captured_params.update(params)
            return _mock_response(CSV_DAILY_ADJUSTED)

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   side_effect=capture_request):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                get_stock("AAPL", "2020-01-01", "2020-01-05")

        assert captured_params.get("outputsize") == "full"

    def test_rate_limit_error_propagates(self):
        from tradingagents.dataflows.alpha_vantage_stock import get_stock
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(RATE_LIMIT_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                with pytest.raises(AlphaVantageRateLimitError):
                    get_stock("AAPL", "2024-01-01", "2024-01-05")


# ---------------------------------------------------------------------------
# get_fundamentals / get_balance_sheet / get_cashflow / get_income_statement
# (alpha_vantage_fundamentals)
# ---------------------------------------------------------------------------

class TestAlphaVantageGetFundamentals:
    """Tests for Alpha Vantage get_fundamentals."""

    def test_returns_json_string_on_success(self):
        from tradingagents.dataflows.alpha_vantage_fundamentals import get_fundamentals

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(OVERVIEW_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_fundamentals("AAPL")

        assert "Apple Inc" in result
        assert "TECHNOLOGY" in result

    def test_rate_limit_error_propagates(self):
        from tradingagents.dataflows.alpha_vantage_fundamentals import get_fundamentals
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(RATE_LIMIT_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                with pytest.raises(AlphaVantageRateLimitError):
                    get_fundamentals("AAPL")


class TestAlphaVantageGetBalanceSheet:
    def test_returns_response_text_on_success(self):
        from tradingagents.dataflows.alpha_vantage_fundamentals import get_balance_sheet

        payload = json.dumps({"symbol": "AAPL", "annualReports": [], "quarterlyReports": []})
        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(payload)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_balance_sheet("AAPL")

        assert "AAPL" in result


class TestAlphaVantageGetCashflow:
    def test_returns_response_text_on_success(self):
        from tradingagents.dataflows.alpha_vantage_fundamentals import get_cashflow

        payload = json.dumps({"symbol": "AAPL", "annualReports": [], "quarterlyReports": []})
        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(payload)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_cashflow("AAPL")

        assert "AAPL" in result


class TestAlphaVantageGetIncomeStatement:
    def test_returns_response_text_on_success(self):
        from tradingagents.dataflows.alpha_vantage_fundamentals import get_income_statement

        payload = json.dumps({"symbol": "AAPL", "annualReports": [], "quarterlyReports": []})
        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(payload)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_income_statement("AAPL")

        assert "AAPL" in result


# ---------------------------------------------------------------------------
# get_news / get_global_news / get_insider_transactions (alpha_vantage_news)
# ---------------------------------------------------------------------------

NEWS_JSON = json.dumps({
    "feed": [
        {
            "title": "Apple Hits Record High",
            "url": "https://example.com/news/1",
            "time_published": "20240105T150000",
            "authors": ["John Doe"],
            "summary": "Apple stock reached a new record.",
            "overall_sentiment_label": "Bullish",
        }
    ]
})

INSIDER_JSON = json.dumps({
    "data": [
        {
            "executive": "Tim Cook",
            "transactionDate": "2024-01-15",
            "transactionType": "Sale",
            "sharesTraded": "10000",
            "sharePrice": "150.00",
        }
    ]
})


class TestAlphaVantageGetNews:
    def test_returns_news_response_on_success(self):
        from tradingagents.dataflows.alpha_vantage_news import get_news

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(NEWS_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_news("AAPL", "2024-01-01", "2024-01-05")

        assert "Apple Hits Record High" in result

    def test_rate_limit_error_propagates(self):
        from tradingagents.dataflows.alpha_vantage_news import get_news
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(RATE_LIMIT_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                with pytest.raises(AlphaVantageRateLimitError):
                    get_news("AAPL", "2024-01-01", "2024-01-05")


class TestAlphaVantageGetGlobalNews:
    def test_returns_global_news_response_on_success(self):
        from tradingagents.dataflows.alpha_vantage_news import get_global_news

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(NEWS_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_global_news("2024-01-15", look_back_days=7)

        assert isinstance(result, str)

    def test_look_back_days_affects_time_from_param(self):
        """The time_from parameter should reflect the look_back_days offset."""
        from tradingagents.dataflows.alpha_vantage_news import get_global_news

        captured_params = {}

        def capture(url, params):
            captured_params.update(params)
            return _mock_response(NEWS_JSON)

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   side_effect=capture):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                get_global_news("2024-01-15", look_back_days=7)

        # time_from should be 7 days before 2024-01-15 → 2024-01-08
        assert "20240108T0000" in captured_params.get("time_from", "")


class TestAlphaVantageGetInsiderTransactions:
    def test_returns_insider_data_on_success(self):
        from tradingagents.dataflows.alpha_vantage_news import get_insider_transactions

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(INSIDER_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_insider_transactions("AAPL")

        assert "Tim Cook" in result

    def test_rate_limit_error_propagates(self):
        from tradingagents.dataflows.alpha_vantage_news import get_insider_transactions
        from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(RATE_LIMIT_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                with pytest.raises(AlphaVantageRateLimitError):
                    get_insider_transactions("AAPL")


# ---------------------------------------------------------------------------
# get_indicator (alpha_vantage_indicator)
# ---------------------------------------------------------------------------

class TestAlphaVantageGetIndicator:
    """Tests for the Alpha Vantage get_indicator function."""

    def test_rsi_returns_formatted_string_on_success(self):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(CSV_RSI)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_indicator(
                    "AAPL", "rsi", "2024-01-05", look_back_days=5
                )

        assert isinstance(result, str)
        assert "RSI" in result.upper()

    def test_sma_50_returns_formatted_string_on_success(self):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(CSV_SMA)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_indicator(
                    "AAPL", "close_50_sma", "2024-01-05", look_back_days=5
                )

        assert isinstance(result, str)
        assert "SMA" in result.upper()

    def test_unsupported_indicator_raises_value_error(self):
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        with pytest.raises(ValueError, match="not supported"):
            get_indicator("AAPL", "unsupported_indicator", "2024-01-05", look_back_days=5)

    def test_rate_limit_error_surfaces_as_error_string(self):
        """Rate limit errors during indicator fetch result in an error string (not a raise)."""
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        with patch("tradingagents.dataflows.alpha_vantage_common.requests.get",
                   return_value=_mock_response(RATE_LIMIT_JSON)):
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
                result = get_indicator("AAPL", "rsi", "2024-01-05", look_back_days=5)

        assert "Error" in result or "rate limit" in result.lower()

    def test_vwma_returns_informational_message(self):
        """VWMA is not directly available; a descriptive message is returned."""
        from tradingagents.dataflows.alpha_vantage_indicator import get_indicator

        with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
            result = get_indicator("AAPL", "vwma", "2024-01-05", look_back_days=5)

        assert "VWMA" in result
        assert "not directly available" in result.lower() or "Volume Weighted" in result
