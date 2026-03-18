"""Offline integration tests for the Finnhub dataflow modules.

All HTTP calls are patched with unittest.mock so no real network requests are
made and no FINNHUB_API_KEY is required.  Mock responses reproduce realistic
Finnhub response shapes to exercise every significant code path.

Run with:
    pytest tests/test_finnhub_integration.py -v
"""

import json
import os
import time
from unittest.mock import MagicMock, call, patch

import pytest
import requests


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_fake_api_key(monkeypatch):
    """Inject a dummy API key so every test bypasses the missing-key guard."""
    monkeypatch.setenv("FINNHUB_API_KEY", "test_key")


# ---------------------------------------------------------------------------
# Shared mock-response helpers
# ---------------------------------------------------------------------------


def _json_response(payload: dict | list, status_code: int = 200) -> MagicMock:
    """Return a mock requests.Response whose .json() returns *payload*."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = json.dumps(payload)
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _error_response(status_code: int, body: str = "") -> MagicMock:
    """Return a mock response with a non-2xx status code."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = body
    resp.json.side_effect = ValueError("not json")
    resp.raise_for_status.side_effect = requests.HTTPError(f"{status_code}")
    return resp


# ---------------------------------------------------------------------------
# Canned response payloads
# ---------------------------------------------------------------------------

CANDLE_OK = {
    "s": "ok",
    "t": [1704067200, 1704153600, 1704240000],  # 2024-01-01 .. 2024-01-03
    "o": [185.0, 186.0, 187.0],
    "h": [188.0, 189.0, 190.0],
    "l": [184.0, 185.0, 186.0],
    "c": [187.0, 188.0, 189.0],
    "v": [50_000_000, 45_000_000, 48_000_000],
}

CANDLE_NO_DATA = {"s": "no_data"}

CANDLE_ERROR_STATUS = {"s": "error"}

QUOTE_OK = {
    "c": 189.5,
    "d": 1.5,
    "dp": 0.8,
    "h": 191.0,
    "l": 187.0,
    "o": 188.0,
    "pc": 188.0,
    "t": 1704153600,
}

QUOTE_ALL_ZERO = {"c": 0.0, "d": 0.0, "dp": 0.0, "h": 0.0, "l": 0.0, "o": 0.0, "pc": 0.0, "t": 0}

PROFILE_OK = {
    "name": "Apple Inc",
    "ticker": "AAPL",
    "exchange": "NASDAQ/NMS (GLOBAL MARKET)",
    "ipo": "1980-12-12",
    "finnhubIndustry": "Technology",
    "marketCapitalization": 2_900_000.0,
    "shareOutstanding": 15_500.0,
    "currency": "USD",
    "country": "US",
    "weburl": "https://www.apple.com/",
    "logo": "https://static.finnhub.io/logo/87cb30d8-80df-11ea-8951-00000000092a.png",
    "phone": "14089961010",
}

FINANCIALS_OK = {
    "cik": "0000320193",
    "data": [
        {
            "period": "2023-12-30",
            "year": 2023,
            "quarter": 1,
            "filedDate": "2024-02-02",
            "acceptedDate": "2024-02-02",
            "form": "10-Q",
            "cik": "0000320193",
            "report": {
                "ic": [
                    {
                        "concept": "us-gaap:Revenues",
                        "label": "Revenues",
                        "unit": "USD",
                        "value": 119_575_000_000,
                    },
                    {
                        "concept": "us-gaap:NetIncomeLoss",
                        "label": "Net Income",
                        "unit": "USD",
                        "value": 33_916_000_000,
                    },
                ],
                "bs": [],
                "cf": [],
            },
        }
    ],
}

FINANCIALS_EMPTY = {"data": []}

METRIC_OK = {
    "metric": {
        "peTTM": 28.5,
        "peAnnual": 29.1,
        "pbQuarterly": 45.2,
        "pbAnnual": 46.0,
        "psTTM": 7.3,
        "52WeekHigh": 199.0,
        "52WeekLow": 124.0,
        "roeTTM": 147.0,
        "roaTTM": 28.0,
        "epsTTM": 6.42,
        "dividendYieldIndicatedAnnual": 0.54,
        "beta": 1.25,
    },
    "series": {},
}

METRIC_EMPTY = {"metric": {}}

COMPANY_NEWS_OK = [
    {
        "headline": "Apple Unveils New iPhone Model",
        "source": "Reuters",
        "summary": "Apple announced its latest device lineup at an event in Cupertino.",
        "url": "https://example.com/news/apple-iphone",
        "datetime": 1704153600,
        "category": "technology",
        "sentiment": 0.4,
    }
]

MARKET_NEWS_OK = [
    {
        "headline": "Fed Signals Rate Pause Ahead",
        "source": "Bloomberg",
        "summary": "Federal Reserve officials indicated they may hold rates steady.",
        "url": "https://example.com/news/fed",
        "datetime": 1704153600,
    }
]

INSIDER_TXN_OK = {
    "data": [
        {
            "name": "Tim Cook",
            "transactionCode": "S",
            "share": 100_000,
            "price": 185.5,
            "value": 18_550_000.0,
            "transactionDate": "2024-01-10",
            "filingDate": "2024-01-12",
        }
    ]
}

INSIDER_TXN_EMPTY = {"data": []}

INDICATOR_RSI_OK = {
    "s": "ok",
    "t": [1704067200, 1704153600],
    "rsi": [62.5, 64.1],
}

INDICATOR_MACD_OK = {
    "s": "ok",
    "t": [1704067200, 1704153600],
    "macd": [1.23, 1.45],
    "macdSignal": [1.10, 1.30],
    "macdHist": [0.13, 0.15],
}

INDICATOR_BBANDS_OK = {
    "s": "ok",
    "t": [1704067200, 1704153600],
    "upperBand": [195.0, 196.0],
    "middleBand": [185.0, 186.0],
    "lowerBand": [175.0, 176.0],
}

INDICATOR_NO_DATA = {"s": "no_data", "t": []}


# ---------------------------------------------------------------------------
# 1. finnhub_common — Exception hierarchy
# ---------------------------------------------------------------------------


class TestFinnhubExceptionHierarchy:
    """All custom exceptions must be proper subclasses of FinnhubError."""

    def test_finnhub_error_is_exception(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError

        assert issubclass(FinnhubError, Exception)

    def test_api_key_invalid_error_is_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import APIKeyInvalidError, FinnhubError

        assert issubclass(APIKeyInvalidError, FinnhubError)

    def test_rate_limit_error_is_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError, RateLimitError

        assert issubclass(RateLimitError, FinnhubError)

    def test_third_party_error_is_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError, ThirdPartyError

        assert issubclass(ThirdPartyError, FinnhubError)

    def test_third_party_timeout_error_is_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError, ThirdPartyTimeoutError

        assert issubclass(ThirdPartyTimeoutError, FinnhubError)

    def test_third_party_parse_error_is_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError, ThirdPartyParseError

        assert issubclass(ThirdPartyParseError, FinnhubError)

    def test_all_exceptions_can_be_raised_and_caught(self):
        from tradingagents.dataflows.finnhub_common import (
            APIKeyInvalidError,
            FinnhubError,
            RateLimitError,
            ThirdPartyError,
            ThirdPartyParseError,
            ThirdPartyTimeoutError,
        )

        for exc_class in (
            APIKeyInvalidError,
            RateLimitError,
            ThirdPartyError,
            ThirdPartyTimeoutError,
            ThirdPartyParseError,
        ):
            with pytest.raises(FinnhubError):
                raise exc_class("test message")


# ---------------------------------------------------------------------------
# 2. finnhub_common — get_api_key
# ---------------------------------------------------------------------------


class TestGetApiKey:
    """get_api_key() reads from env; raises APIKeyInvalidError when absent."""

    def test_returns_key_when_set(self):
        from tradingagents.dataflows.finnhub_common import get_api_key

        # autouse fixture already sets FINNHUB_API_KEY=test_key
        assert get_api_key() == "test_key"

    def test_raises_when_env_var_missing(self, monkeypatch):
        from tradingagents.dataflows.finnhub_common import APIKeyInvalidError, get_api_key

        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
        with pytest.raises(APIKeyInvalidError, match="FINNHUB_API_KEY"):
            get_api_key()

    def test_raises_when_env_var_empty_string(self, monkeypatch):
        from tradingagents.dataflows.finnhub_common import APIKeyInvalidError, get_api_key

        monkeypatch.setenv("FINNHUB_API_KEY", "")
        with pytest.raises(APIKeyInvalidError):
            get_api_key()


# ---------------------------------------------------------------------------
# 3. finnhub_common — _make_api_request HTTP status mapping
# ---------------------------------------------------------------------------


class TestMakeApiRequest:
    """_make_api_request maps HTTP status codes to the correct exceptions."""

    _PATCH_TARGET = "tradingagents.dataflows.finnhub_common.requests.get"

    def test_success_returns_dict(self):
        from tradingagents.dataflows.finnhub_common import _make_api_request

        with patch(self._PATCH_TARGET, return_value=_json_response({"foo": "bar"})):
            result = _make_api_request("quote", {"symbol": "AAPL"})

        assert result == {"foo": "bar"}

    def test_http_401_raises_api_key_invalid_error(self):
        from tradingagents.dataflows.finnhub_common import APIKeyInvalidError, _make_api_request

        with patch(self._PATCH_TARGET, return_value=_error_response(401, "Unauthorized")):
            with pytest.raises(APIKeyInvalidError):
                _make_api_request("quote", {"symbol": "AAPL"})

    def test_http_403_raises_api_key_invalid_error(self):
        from tradingagents.dataflows.finnhub_common import APIKeyInvalidError, _make_api_request

        with patch(self._PATCH_TARGET, return_value=_error_response(403, "Forbidden")):
            with pytest.raises(APIKeyInvalidError):
                _make_api_request("quote", {"symbol": "AAPL"})

    def test_http_429_raises_rate_limit_error(self):
        from tradingagents.dataflows.finnhub_common import RateLimitError, _make_api_request

        with patch(self._PATCH_TARGET, return_value=_error_response(429, "Too Many Requests")):
            with pytest.raises(RateLimitError):
                _make_api_request("quote", {"symbol": "AAPL"})

    def test_http_500_raises_third_party_error(self):
        from tradingagents.dataflows.finnhub_common import ThirdPartyError, _make_api_request

        with patch(self._PATCH_TARGET, return_value=_error_response(500, "Internal Server Error")):
            with pytest.raises(ThirdPartyError):
                _make_api_request("quote", {"symbol": "AAPL"})

    def test_timeout_raises_third_party_timeout_error(self):
        from tradingagents.dataflows.finnhub_common import (
            ThirdPartyTimeoutError,
            _make_api_request,
        )

        with patch(
            self._PATCH_TARGET, side_effect=requests.exceptions.Timeout("timed out")
        ):
            with pytest.raises(ThirdPartyTimeoutError):
                _make_api_request("quote", {"symbol": "AAPL"})

    def test_connection_error_raises_third_party_error(self):
        from tradingagents.dataflows.finnhub_common import ThirdPartyError, _make_api_request

        with patch(
            self._PATCH_TARGET,
            side_effect=requests.exceptions.ConnectionError("connection refused"),
        ):
            with pytest.raises(ThirdPartyError):
                _make_api_request("quote", {"symbol": "AAPL"})

    def test_bad_json_raises_third_party_parse_error(self):
        from tradingagents.dataflows.finnhub_common import (
            ThirdPartyParseError,
            _make_api_request,
        )

        bad_resp = MagicMock()
        bad_resp.status_code = 200
        bad_resp.text = "not-json!!"
        bad_resp.json.side_effect = ValueError("invalid json")
        bad_resp.raise_for_status = MagicMock()

        with patch(self._PATCH_TARGET, return_value=bad_resp):
            with pytest.raises(ThirdPartyParseError):
                _make_api_request("quote", {"symbol": "AAPL"})

    def test_token_is_injected_into_request_params(self):
        """The API key must be passed as 'token' in the query params."""
        from tradingagents.dataflows.finnhub_common import _make_api_request

        captured = {}

        def capture(url, params, **kwargs):
            captured.update(params)
            return _json_response({})

        with patch(self._PATCH_TARGET, side_effect=capture):
            _make_api_request("quote", {"symbol": "AAPL"})

        assert captured.get("token") == "test_key"


# ---------------------------------------------------------------------------
# 4. finnhub_common — utility helpers
# ---------------------------------------------------------------------------


class TestToUnixTimestamp:
    """_to_unix_timestamp converts YYYY-MM-DD strings to integer Unix timestamps."""

    def test_known_date_returns_integer(self):
        from tradingagents.dataflows.finnhub_common import _to_unix_timestamp

        result = _to_unix_timestamp("2024-01-15")
        assert isinstance(result, int)
        # 2024-01-15 00:00 UTC+0 is 1705276800; local TZ may shift ±hours but
        # the date portion is always in range [1705190400, 1705363200]
        assert 1705190400 <= result <= 1705363200

    def test_invalid_format_raises_value_error(self):
        from tradingagents.dataflows.finnhub_common import _to_unix_timestamp

        with pytest.raises(ValueError):
            _to_unix_timestamp("15-01-2024")

    def test_non_date_string_raises_value_error(self):
        from tradingagents.dataflows.finnhub_common import _to_unix_timestamp

        with pytest.raises(ValueError):
            _to_unix_timestamp("not-a-date")


class TestFmtPct:
    """_fmt_pct formats floats as signed percentage strings."""

    def test_positive_float(self):
        from tradingagents.dataflows.finnhub_common import _fmt_pct

        assert _fmt_pct(1.23) == "+1.23%"

    def test_negative_float(self):
        from tradingagents.dataflows.finnhub_common import _fmt_pct

        assert _fmt_pct(-4.56) == "-4.56%"

    def test_zero(self):
        from tradingagents.dataflows.finnhub_common import _fmt_pct

        assert _fmt_pct(0.0) == "+0.00%"

    def test_none_returns_na(self):
        from tradingagents.dataflows.finnhub_common import _fmt_pct

        assert _fmt_pct(None) == "N/A"


# ---------------------------------------------------------------------------
# 5. finnhub_stock — get_stock_candles
# ---------------------------------------------------------------------------


class TestGetStockCandles:
    """get_stock_candles returns a CSV string or raises FinnhubError."""

    _PATCH_TARGET = "tradingagents.dataflows.finnhub_common.requests.get"

    def test_ok_response_produces_csv_with_header(self):
        from tradingagents.dataflows.finnhub_stock import get_stock_candles

        with patch(self._PATCH_TARGET, return_value=_json_response(CANDLE_OK)):
            result = get_stock_candles("AAPL", "2024-01-01", "2024-01-03")

        lines = result.strip().split("\n")
        assert lines[0] == "timestamp,open,high,low,close,volume"
        assert len(lines) >= 2, "Expected at least one data row"

    def test_ok_response_data_rows_contain_price(self):
        from tradingagents.dataflows.finnhub_stock import get_stock_candles

        with patch(self._PATCH_TARGET, return_value=_json_response(CANDLE_OK)):
            result = get_stock_candles("AAPL", "2024-01-01", "2024-01-03")

        # Each data row should have 6 comma-separated fields
        data_rows = result.strip().split("\n")[1:]
        for row in data_rows:
            fields = row.split(",")
            assert len(fields) == 6

    def test_no_data_status_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_stock import get_stock_candles

        with patch(self._PATCH_TARGET, return_value=_json_response(CANDLE_NO_DATA)):
            with pytest.raises(FinnhubError):
                get_stock_candles("INVALID", "2024-01-01", "2024-01-03")

    def test_error_status_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_stock import get_stock_candles

        with patch(self._PATCH_TARGET, return_value=_json_response(CANDLE_ERROR_STATUS)):
            with pytest.raises(FinnhubError):
                get_stock_candles("AAPL", "2024-01-01", "2024-01-03")

    def test_ok_with_empty_timestamps_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_stock import get_stock_candles

        empty_candle = {"s": "ok", "t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
        with patch(self._PATCH_TARGET, return_value=_json_response(empty_candle)):
            with pytest.raises(FinnhubError):
                get_stock_candles("AAPL", "2024-01-01", "2024-01-03")


# ---------------------------------------------------------------------------
# 6. finnhub_stock — get_quote
# ---------------------------------------------------------------------------


class TestGetQuote:
    """get_quote returns a normalised dict or raises FinnhubError."""

    _PATCH_TARGET = "tradingagents.dataflows.finnhub_common.requests.get"

    def test_ok_response_returns_expected_keys(self):
        from tradingagents.dataflows.finnhub_stock import get_quote

        with patch(self._PATCH_TARGET, return_value=_json_response(QUOTE_OK)):
            result = get_quote("AAPL")

        expected_keys = {
            "symbol", "current_price", "change", "change_percent",
            "high", "low", "open", "prev_close", "timestamp",
        }
        assert expected_keys == set(result.keys())

    def test_ok_response_symbol_field_is_correct(self):
        from tradingagents.dataflows.finnhub_stock import get_quote

        with patch(self._PATCH_TARGET, return_value=_json_response(QUOTE_OK)):
            result = get_quote("AAPL")

        assert result["symbol"] == "AAPL"

    def test_ok_response_prices_are_floats(self):
        from tradingagents.dataflows.finnhub_stock import get_quote

        with patch(self._PATCH_TARGET, return_value=_json_response(QUOTE_OK)):
            result = get_quote("AAPL")

        assert isinstance(result["current_price"], float)
        assert isinstance(result["change_percent"], float)

    def test_all_zero_response_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_stock import get_quote

        with patch(self._PATCH_TARGET, return_value=_json_response(QUOTE_ALL_ZERO)):
            with pytest.raises(FinnhubError, match="all-zero"):
                get_quote("BADINVLDSYM")

    def test_timestamp_absent_uses_now_string(self):
        """When t=0 (no timestamp), the fallback is a formatted 'now' string."""
        from tradingagents.dataflows.finnhub_stock import get_quote

        quote_no_ts = dict(QUOTE_OK)
        quote_no_ts["t"] = 0

        with patch(self._PATCH_TARGET, return_value=_json_response(quote_no_ts)):
            result = get_quote("AAPL")

        # Timestamp must be a non-empty string
        assert isinstance(result["timestamp"], str)
        assert result["timestamp"]


# ---------------------------------------------------------------------------
# 7. finnhub_fundamentals — get_company_profile
# ---------------------------------------------------------------------------


class TestGetCompanyProfile:
    """get_company_profile returns a formatted string or raises FinnhubError."""

    _PATCH_TARGET = "tradingagents.dataflows.finnhub_common.requests.get"

    def test_ok_response_contains_company_name(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_company_profile

        with patch(self._PATCH_TARGET, return_value=_json_response(PROFILE_OK)):
            result = get_company_profile("AAPL")

        assert "Apple Inc" in result

    def test_ok_response_contains_symbol(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_company_profile

        with patch(self._PATCH_TARGET, return_value=_json_response(PROFILE_OK)):
            result = get_company_profile("AAPL")

        assert "AAPL" in result

    def test_ok_response_contains_exchange(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_company_profile

        with patch(self._PATCH_TARGET, return_value=_json_response(PROFILE_OK)):
            result = get_company_profile("AAPL")

        assert "NASDAQ" in result

    def test_empty_profile_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_fundamentals import get_company_profile

        with patch(self._PATCH_TARGET, return_value=_json_response({})):
            with pytest.raises(FinnhubError):
                get_company_profile("BADINVLDSYM")

    def test_result_is_multiline_string(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_company_profile

        with patch(self._PATCH_TARGET, return_value=_json_response(PROFILE_OK)):
            result = get_company_profile("AAPL")

        assert "\n" in result


# ---------------------------------------------------------------------------
# 8. finnhub_fundamentals — get_financial_statements
# ---------------------------------------------------------------------------


class TestGetFinancialStatements:
    """get_financial_statements returns formatted text or raises on errors."""

    _PATCH_TARGET = "tradingagents.dataflows.finnhub_common.requests.get"

    def test_income_statement_ok_has_header(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_financial_statements

        with patch(self._PATCH_TARGET, return_value=_json_response(FINANCIALS_OK)):
            result = get_financial_statements("AAPL", "income_statement", "quarterly")

        # Header should mention the statement type and symbol
        assert "AAPL" in result
        assert "Income Statement" in result or "income_statement" in result.lower()

    def test_income_statement_ok_contains_line_items(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_financial_statements

        with patch(self._PATCH_TARGET, return_value=_json_response(FINANCIALS_OK)):
            result = get_financial_statements("AAPL", "income_statement", "quarterly")

        assert "Revenues" in result or "Net Income" in result

    def test_empty_data_list_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_fundamentals import get_financial_statements

        with patch(self._PATCH_TARGET, return_value=_json_response(FINANCIALS_EMPTY)):
            with pytest.raises(FinnhubError, match="No financial reports"):
                get_financial_statements("AAPL", "income_statement", "quarterly")

    def test_invalid_statement_type_raises_value_error(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_financial_statements

        with pytest.raises(ValueError, match="Invalid statement_type"):
            get_financial_statements("AAPL", "invalid_type", "quarterly")  # type: ignore[arg-type]

    def test_balance_sheet_and_cash_flow_accepted(self):
        """Both 'balance_sheet' and 'cash_flow' are valid statement_type values."""
        from tradingagents.dataflows.finnhub_fundamentals import get_financial_statements

        # Build a payload with bs and cf data present
        bs_payload = {
            "data": [
                {
                    "period": "2023-12-30",
                    "year": 2023,
                    "quarter": 1,
                    "filedDate": "2024-02-02",
                    "acceptedDate": "2024-02-02",
                    "form": "10-Q",
                    "cik": "0000320193",
                    "report": {
                        "bs": [{"concept": "us-gaap:Assets", "label": "Assets", "unit": "USD", "value": 352_583_000_000}],
                        "ic": [],
                        "cf": [],
                    },
                }
            ]
        }

        with patch(self._PATCH_TARGET, return_value=_json_response(bs_payload)):
            result = get_financial_statements("AAPL", "balance_sheet", "annual")

        assert "AAPL" in result


# ---------------------------------------------------------------------------
# 9. finnhub_fundamentals — get_basic_financials
# ---------------------------------------------------------------------------


class TestGetBasicFinancials:
    """get_basic_financials returns formatted metrics or raises FinnhubError."""

    _PATCH_TARGET = "tradingagents.dataflows.finnhub_common.requests.get"

    def test_ok_response_contains_valuation_header(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_basic_financials

        with patch(self._PATCH_TARGET, return_value=_json_response(METRIC_OK)):
            result = get_basic_financials("AAPL")

        assert "Valuation" in result

    def test_ok_response_contains_symbol(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_basic_financials

        with patch(self._PATCH_TARGET, return_value=_json_response(METRIC_OK)):
            result = get_basic_financials("AAPL")

        assert "AAPL" in result

    def test_ok_response_has_pe_metric(self):
        from tradingagents.dataflows.finnhub_fundamentals import get_basic_financials

        with patch(self._PATCH_TARGET, return_value=_json_response(METRIC_OK)):
            result = get_basic_financials("AAPL")

        assert "P/E" in result

    def test_empty_metric_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_fundamentals import get_basic_financials

        with patch(self._PATCH_TARGET, return_value=_json_response(METRIC_EMPTY)):
            with pytest.raises(FinnhubError):
                get_basic_financials("BADINVLDSYM")

    def test_missing_optional_metrics_rendered_as_na(self):
        """Metrics absent from the payload should appear as 'N/A' in output."""
        from tradingagents.dataflows.finnhub_fundamentals import get_basic_financials

        sparse_metric = {"metric": {"peTTM": 25.0}}  # all others absent
        with patch(self._PATCH_TARGET, return_value=_json_response(sparse_metric)):
            result = get_basic_financials("AAPL")

        assert "N/A" in result


# ---------------------------------------------------------------------------
# 10. finnhub_news — get_company_news
# ---------------------------------------------------------------------------


class TestGetCompanyNews:
    """get_company_news returns formatted markdown or 'no news' fallback."""

    _PATCH_TARGET = "tradingagents.dataflows.finnhub_common.requests.get"

    def test_ok_response_contains_headline(self):
        from tradingagents.dataflows.finnhub_news import get_company_news

        with patch(self._PATCH_TARGET, return_value=_json_response(COMPANY_NEWS_OK)):
            result = get_company_news("AAPL", "2024-01-01", "2024-01-10")

        assert "Apple Unveils New iPhone Model" in result

    def test_ok_response_contains_source(self):
        from tradingagents.dataflows.finnhub_news import get_company_news

        with patch(self._PATCH_TARGET, return_value=_json_response(COMPANY_NEWS_OK)):
            result = get_company_news("AAPL", "2024-01-01", "2024-01-10")

        assert "Reuters" in result

    def test_empty_articles_list_returns_no_news_message(self):
        from tradingagents.dataflows.finnhub_news import get_company_news

        with patch(self._PATCH_TARGET, return_value=_json_response([])):
            result = get_company_news("AAPL", "2024-01-01", "2024-01-10")

        assert "No news articles" in result

    def test_result_has_symbol_in_header(self):
        from tradingagents.dataflows.finnhub_news import get_company_news

        with patch(self._PATCH_TARGET, return_value=_json_response(COMPANY_NEWS_OK)):
            result = get_company_news("AAPL", "2024-01-01", "2024-01-10")

        assert "AAPL" in result


# ---------------------------------------------------------------------------
# 11. finnhub_news — get_market_news
# ---------------------------------------------------------------------------


class TestGetMarketNews:
    """get_market_news returns formatted news or raises on invalid categories."""

    _PATCH_TARGET = "tradingagents.dataflows.finnhub_common.requests.get"

    def test_general_category_contains_market_news_header(self):
        from tradingagents.dataflows.finnhub_news import get_market_news

        with patch(self._PATCH_TARGET, return_value=_json_response(MARKET_NEWS_OK)):
            result = get_market_news("general")

        assert "Market News" in result

    def test_valid_categories_accepted(self):
        """All four valid categories should not raise ValueError."""
        from tradingagents.dataflows.finnhub_news import get_market_news

        for category in ("general", "forex", "crypto", "merger"):
            with patch(self._PATCH_TARGET, return_value=_json_response([])):
                result = get_market_news(category)  # should not raise
            assert isinstance(result, str)

    def test_invalid_category_raises_value_error(self):
        from tradingagents.dataflows.finnhub_news import get_market_news

        with pytest.raises(ValueError, match="Invalid category"):
            get_market_news("sports")  # type: ignore[arg-type]

    def test_ok_response_contains_headline(self):
        from tradingagents.dataflows.finnhub_news import get_market_news

        with patch(self._PATCH_TARGET, return_value=_json_response(MARKET_NEWS_OK)):
            result = get_market_news("general")

        assert "Fed Signals Rate Pause Ahead" in result


# ---------------------------------------------------------------------------
# 12. finnhub_news — get_insider_transactions
# ---------------------------------------------------------------------------


class TestGetInsiderTransactions:
    """get_insider_transactions returns a markdown table or 'no transactions' fallback."""

    _PATCH_TARGET = "tradingagents.dataflows.finnhub_common.requests.get"

    def test_ok_response_has_markdown_table_header(self):
        from tradingagents.dataflows.finnhub_news import get_insider_transactions

        with patch(self._PATCH_TARGET, return_value=_json_response(INSIDER_TXN_OK)):
            result = get_insider_transactions("AAPL")

        # Markdown table header row
        assert "| Name |" in result or "|Name|" in result.replace(" ", "")

    def test_ok_response_contains_executive_name(self):
        from tradingagents.dataflows.finnhub_news import get_insider_transactions

        with patch(self._PATCH_TARGET, return_value=_json_response(INSIDER_TXN_OK)):
            result = get_insider_transactions("AAPL")

        assert "Tim Cook" in result

    def test_ok_response_transaction_code_mapped_to_label(self):
        """Transaction code 'S' should be rendered as 'Sell', not 'S'."""
        from tradingagents.dataflows.finnhub_news import get_insider_transactions

        with patch(self._PATCH_TARGET, return_value=_json_response(INSIDER_TXN_OK)):
            result = get_insider_transactions("AAPL")

        assert "Sell" in result

    def test_empty_transactions_returns_no_transactions_message(self):
        from tradingagents.dataflows.finnhub_news import get_insider_transactions

        with patch(self._PATCH_TARGET, return_value=_json_response(INSIDER_TXN_EMPTY)):
            result = get_insider_transactions("AAPL")

        assert "No insider transactions" in result

    def test_result_contains_symbol(self):
        from tradingagents.dataflows.finnhub_news import get_insider_transactions

        with patch(self._PATCH_TARGET, return_value=_json_response(INSIDER_TXN_OK)):
            result = get_insider_transactions("AAPL")

        assert "AAPL" in result


# ---------------------------------------------------------------------------
# 13. finnhub_scanner — get_market_movers_finnhub
# ---------------------------------------------------------------------------


def _make_quote_side_effect(symbols_quotes: dict) -> callable:
    """Build a side_effect for _rate_limited_request that returns quote data per symbol."""

    def side_effect(endpoint: str, params: dict) -> dict:
        symbol = params.get("symbol", "")
        if symbol in symbols_quotes:
            return symbols_quotes[symbol]
        # Default: valid but flat quote so it is not skipped
        return {"c": 100.0, "d": 0.0, "dp": 0.0, "h": 101.0, "l": 99.0, "o": 100.0, "pc": 100.0, "t": 1704153600}

    return side_effect


class TestGetMarketMoversFinnnhub:
    """get_market_movers_finnhub returns a sorted markdown table."""

    _RATE_PATCH = "tradingagents.dataflows.finnhub_scanner._rate_limited_request"

    def _build_movers_side_effect(self) -> callable:
        """Return a mock that assigns unique change% values to the first few symbols."""
        quotes_by_symbol = {
            "AAPL": {"c": 200.0, "d": 5.0, "dp": 2.5, "h": 202.0, "l": 198.0, "o": 195.0, "pc": 195.0, "t": 1704153600},
            "MSFT": {"c": 400.0, "d": 3.0, "dp": 0.75, "h": 402.0, "l": 398.0, "o": 397.0, "pc": 397.0, "t": 1704153600},
            "NVDA": {"c": 600.0, "d": 30.0, "dp": 5.26, "h": 605.0, "l": 595.0, "o": 570.0, "pc": 570.0, "t": 1704153600},
        }
        return _make_quote_side_effect(quotes_by_symbol)

    def test_gainers_returns_markdown_table(self):
        from tradingagents.dataflows.finnhub_scanner import get_market_movers_finnhub

        with patch(self._RATE_PATCH, side_effect=self._build_movers_side_effect()):
            result = get_market_movers_finnhub("gainers")

        assert "| Symbol |" in result or "|Symbol|" in result.replace(" ", "")

    def test_gainers_sorted_highest_first(self):
        """The first data row after the header should be the top gainer."""
        from tradingagents.dataflows.finnhub_scanner import get_market_movers_finnhub

        with patch(self._RATE_PATCH, side_effect=self._build_movers_side_effect()):
            result = get_market_movers_finnhub("gainers")

        # NVDA has the highest dp (+5.26%) so it must appear before AAPL (+2.5%)
        nvda_pos = result.find("NVDA")
        aapl_pos = result.find("AAPL")
        assert nvda_pos != -1
        assert nvda_pos < aapl_pos

    def test_losers_sorted_lowest_first(self):
        from tradingagents.dataflows.finnhub_scanner import get_market_movers_finnhub

        losers_quotes = {
            "AAPL": {"c": 180.0, "d": -5.0, "dp": -2.7, "h": 186.0, "l": 179.0, "o": 185.0, "pc": 185.0, "t": 1704153600},
            "MSFT": {"c": 390.0, "d": -1.0, "dp": -0.26, "h": 392.0, "l": 389.0, "o": 391.0, "pc": 391.0, "t": 1704153600},
        }

        with patch(self._RATE_PATCH, side_effect=_make_quote_side_effect(losers_quotes)):
            result = get_market_movers_finnhub("losers")

        aapl_pos = result.find("AAPL")
        msft_pos = result.find("MSFT")
        assert aapl_pos != -1
        assert aapl_pos < msft_pos

    def test_invalid_category_raises_value_error(self):
        from tradingagents.dataflows.finnhub_scanner import get_market_movers_finnhub

        with pytest.raises(ValueError, match="Invalid category"):
            get_market_movers_finnhub("unknown_cat")

    def test_all_quotes_fail_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_scanner import get_market_movers_finnhub

        with patch(
            self._RATE_PATCH,
            side_effect=FinnhubError("quota exceeded"),
        ):
            with pytest.raises(FinnhubError, match="All .* quote fetches failed"):
                get_market_movers_finnhub("gainers")


# ---------------------------------------------------------------------------
# 14. finnhub_scanner — get_market_indices_finnhub
# ---------------------------------------------------------------------------


class TestGetMarketIndicesFinnnhub:
    """get_market_indices_finnhub builds a table of index levels."""

    _RATE_PATCH = "tradingagents.dataflows.finnhub_scanner._rate_limited_request"

    def test_output_contains_major_market_indices_header(self):
        from tradingagents.dataflows.finnhub_scanner import get_market_indices_finnhub

        with patch(self._RATE_PATCH, return_value=QUOTE_OK):
            result = get_market_indices_finnhub()

        assert "Major Market Indices" in result

    def test_output_contains_spy_proxy_label(self):
        from tradingagents.dataflows.finnhub_scanner import get_market_indices_finnhub

        with patch(self._RATE_PATCH, return_value=QUOTE_OK):
            result = get_market_indices_finnhub()

        assert "SPY" in result or "S&P 500" in result

    def test_vix_row_has_no_dollar_sign(self):
        """VIX is unitless — it must not be prefixed with '$'."""
        from tradingagents.dataflows.finnhub_scanner import get_market_indices_finnhub

        with patch(self._RATE_PATCH, return_value=QUOTE_OK):
            result = get_market_indices_finnhub()

        lines = result.split("\n")
        vix_lines = [l for l in lines if "VIX" in l]
        assert vix_lines, "Expected a VIX row"
        # The VIX price cell must not start with '$'
        for vix_line in vix_lines:
            cells = [c.strip() for c in vix_line.split("|") if c.strip()]
            # cells[1] is the Price cell for the VIX row
            if len(cells) >= 2:
                assert not cells[1].startswith("$"), f"VIX price should not have $: {cells[1]}"

    def test_all_fetches_fail_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_scanner import get_market_indices_finnhub

        with patch(
            self._RATE_PATCH,
            side_effect=FinnhubError("network failure"),
        ):
            with pytest.raises(FinnhubError, match="All market index fetches failed"):
                get_market_indices_finnhub()


# ---------------------------------------------------------------------------
# 15. finnhub_scanner — get_sector_performance_finnhub
# ---------------------------------------------------------------------------


class TestGetSectorPerformanceFinnnhub:
    """get_sector_performance_finnhub returns sector ETF data."""

    _RATE_PATCH = "tradingagents.dataflows.finnhub_scanner._rate_limited_request"

    def test_output_contains_sector_performance_header(self):
        from tradingagents.dataflows.finnhub_scanner import get_sector_performance_finnhub

        with patch(self._RATE_PATCH, return_value=QUOTE_OK):
            result = get_sector_performance_finnhub()

        assert "Sector Performance" in result

    def test_output_contains_at_least_one_sector_etf(self):
        from tradingagents.dataflows.finnhub_scanner import get_sector_performance_finnhub

        with patch(self._RATE_PATCH, return_value=QUOTE_OK):
            result = get_sector_performance_finnhub()

        # At least one known sector ETF ticker should appear
        etf_tickers = {"XLK", "XLV", "XLF", "XLE", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC"}
        assert any(ticker in result for ticker in etf_tickers)

    def test_all_sectors_fail_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_scanner import get_sector_performance_finnhub

        with patch(
            self._RATE_PATCH,
            side_effect=FinnhubError("all failed"),
        ):
            with pytest.raises(FinnhubError):
                get_sector_performance_finnhub()


# ---------------------------------------------------------------------------
# 16. finnhub_scanner — get_topic_news_finnhub
# ---------------------------------------------------------------------------


class TestGetTopicNewsFinnnhub:
    """get_topic_news_finnhub maps topic strings to Finnhub categories."""

    _RATE_PATCH = "tradingagents.dataflows.finnhub_scanner._rate_limited_request"

    def test_crypto_topic_output_contains_topic(self):
        from tradingagents.dataflows.finnhub_scanner import get_topic_news_finnhub

        with patch(self._RATE_PATCH, return_value=MARKET_NEWS_OK):
            result = get_topic_news_finnhub("crypto")

        assert "crypto" in result.lower()

    def test_crypto_topic_maps_to_crypto_category(self):
        """Verify the request is made with category='crypto'."""
        from tradingagents.dataflows.finnhub_scanner import get_topic_news_finnhub

        captured_params: list[dict] = []

        def capture(endpoint, params):
            captured_params.append(dict(params))
            return []

        with patch(self._RATE_PATCH, side_effect=capture):
            get_topic_news_finnhub("crypto")

        assert any(p.get("category") == "crypto" for p in captured_params)

    def test_unknown_topic_defaults_to_general_category(self):
        """An unrecognised topic must fall back to 'general', not raise."""
        from tradingagents.dataflows.finnhub_scanner import get_topic_news_finnhub

        captured_params: list[dict] = []

        def capture(endpoint, params):
            captured_params.append(dict(params))
            return []

        with patch(self._RATE_PATCH, side_effect=capture):
            get_topic_news_finnhub("sports_scores")  # unknown topic

        assert any(p.get("category") == "general" for p in captured_params)

    def test_mergers_topic_maps_to_merger_category(self):
        from tradingagents.dataflows.finnhub_scanner import get_topic_news_finnhub

        captured_params: list[dict] = []

        def capture(endpoint, params):
            captured_params.append(dict(params))
            return []

        with patch(self._RATE_PATCH, side_effect=capture):
            get_topic_news_finnhub("mergers")

        assert any(p.get("category") == "merger" for p in captured_params)

    def test_limit_parameter_caps_articles_returned(self):
        """Only the first *limit* articles should appear."""
        from tradingagents.dataflows.finnhub_scanner import get_topic_news_finnhub

        many_articles = [
            {"headline": f"Headline {i}", "source": "src", "summary": "", "url": "", "datetime": 1704153600}
            for i in range(30)
        ]

        with patch(self._RATE_PATCH, return_value=many_articles):
            result = get_topic_news_finnhub("general", limit=5)

        # Only "Headline 0" through "Headline 4" should appear
        assert "Headline 4" in result
        assert "Headline 5" not in result


# ---------------------------------------------------------------------------
# 17. finnhub_indicators — get_indicator_finnhub
# ---------------------------------------------------------------------------


class TestGetIndicatorFinnhub:
    """get_indicator_finnhub returns formatted time-series strings."""

    _PATCH_TARGET = "tradingagents.dataflows.finnhub_common.requests.get"

    def test_rsi_output_has_header_line(self):
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        with patch(self._PATCH_TARGET, return_value=_json_response(INDICATOR_RSI_OK)):
            result = get_indicator_finnhub("AAPL", "rsi", "2024-01-01", "2024-01-05")

        assert "RSI" in result

    def test_rsi_output_has_date_value_rows(self):
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        with patch(self._PATCH_TARGET, return_value=_json_response(INDICATOR_RSI_OK)):
            result = get_indicator_finnhub("AAPL", "rsi", "2024-01-01", "2024-01-05")

        # RSI values should appear: 62.5, 64.1
        assert "62.5" in result or "62.5000" in result

    def test_macd_output_has_multi_column_header(self):
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        with patch(self._PATCH_TARGET, return_value=_json_response(INDICATOR_MACD_OK)):
            result = get_indicator_finnhub("AAPL", "macd", "2024-01-01", "2024-01-05")

        assert "MACD" in result
        assert "Signal" in result
        assert "Histogram" in result

    def test_bbands_output_has_upper_middle_lower_columns(self):
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        with patch(self._PATCH_TARGET, return_value=_json_response(INDICATOR_BBANDS_OK)):
            result = get_indicator_finnhub("AAPL", "bbands", "2024-01-01", "2024-01-05")

        assert "Upper" in result
        assert "Middle" in result
        assert "Lower" in result

    def test_no_data_status_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        with patch(self._PATCH_TARGET, return_value=_json_response(INDICATOR_NO_DATA)):
            with pytest.raises(FinnhubError, match="No indicator data"):
                get_indicator_finnhub("AAPL", "rsi", "2024-01-01", "2024-01-05")

    def test_invalid_indicator_name_raises_value_error(self):
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        with pytest.raises(ValueError, match="not supported"):
            get_indicator_finnhub("AAPL", "bad_indicator", "2024-01-01", "2024-01-05")  # type: ignore[arg-type]

    def test_sma_indicator_accepted(self):
        sma_response = {
            "s": "ok",
            "t": [1704067200, 1704153600],
            "sma": [182.5, 183.1],
        }
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        with patch(self._PATCH_TARGET, return_value=_json_response(sma_response)):
            result = get_indicator_finnhub("AAPL", "sma", "2024-01-01", "2024-01-05")

        assert "SMA" in result

    def test_ema_indicator_accepted(self):
        ema_response = {
            "s": "ok",
            "t": [1704067200],
            "ema": [184.0],
        }
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        with patch(self._PATCH_TARGET, return_value=_json_response(ema_response)):
            result = get_indicator_finnhub("AAPL", "ema", "2024-01-01", "2024-01-05")

        assert "EMA" in result

    def test_atr_indicator_accepted(self):
        atr_response = {
            "s": "ok",
            "t": [1704067200],
            "atr": [3.25],
        }
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        with patch(self._PATCH_TARGET, return_value=_json_response(atr_response)):
            result = get_indicator_finnhub("AAPL", "atr", "2024-01-01", "2024-01-05")

        assert "ATR" in result

    def test_output_contains_symbol_and_date_range(self):
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        with patch(self._PATCH_TARGET, return_value=_json_response(INDICATOR_RSI_OK)):
            result = get_indicator_finnhub("AAPL", "rsi", "2024-01-01", "2024-01-05")

        assert "AAPL" in result
        assert "2024-01-01" in result
        assert "2024-01-05" in result

    def test_output_contains_indicator_description(self):
        """Each indicator should append a human-readable description at the bottom."""
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        with patch(self._PATCH_TARGET, return_value=_json_response(INDICATOR_RSI_OK)):
            result = get_indicator_finnhub("AAPL", "rsi", "2024-01-01", "2024-01-05")

        # The description for RSI includes "overbought"
        assert "overbought" in result.lower() or "RSI" in result

    def test_unexpected_status_raises_finnhub_error(self):
        from tradingagents.dataflows.finnhub_common import FinnhubError
        from tradingagents.dataflows.finnhub_indicators import get_indicator_finnhub

        bad_status = {"s": "error", "t": [1704067200], "rsi": [55.0]}
        with patch(self._PATCH_TARGET, return_value=_json_response(bad_status)):
            with pytest.raises(FinnhubError):
                get_indicator_finnhub("AAPL", "rsi", "2024-01-01", "2024-01-05")


# ---------------------------------------------------------------------------
# 18. Edge cases & cross-cutting concerns
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Cross-cutting edge-case tests that span multiple modules."""

    _PATCH_TARGET = "tradingagents.dataflows.finnhub_common.requests.get"

    def test_api_key_missing_when_calling_stock_candles(self, monkeypatch):
        """All public functions propagate APIKeyInvalidError when key is absent."""
        from tradingagents.dataflows.finnhub_common import APIKeyInvalidError
        from tradingagents.dataflows.finnhub_stock import get_stock_candles

        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
        with pytest.raises(APIKeyInvalidError):
            # No mock needed — key check happens before HTTP call
            get_stock_candles("AAPL", "2024-01-01", "2024-01-03")

    def test_api_key_missing_when_calling_get_quote(self, monkeypatch):
        from tradingagents.dataflows.finnhub_common import APIKeyInvalidError
        from tradingagents.dataflows.finnhub_stock import get_quote

        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
        with pytest.raises(APIKeyInvalidError):
            get_quote("AAPL")

    def test_api_key_missing_when_calling_company_profile(self, monkeypatch):
        from tradingagents.dataflows.finnhub_common import APIKeyInvalidError
        from tradingagents.dataflows.finnhub_fundamentals import get_company_profile

        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
        with pytest.raises(APIKeyInvalidError):
            get_company_profile("AAPL")

    def test_rate_limit_error_propagates_from_stock_candles(self):
        from tradingagents.dataflows.finnhub_common import RateLimitError
        from tradingagents.dataflows.finnhub_stock import get_stock_candles

        with patch(self._PATCH_TARGET, return_value=_error_response(429, "Too Many Requests")):
            with pytest.raises(RateLimitError):
                get_stock_candles("AAPL", "2024-01-01", "2024-01-03")

    def test_rate_limit_error_propagates_from_company_profile(self):
        from tradingagents.dataflows.finnhub_common import RateLimitError
        from tradingagents.dataflows.finnhub_fundamentals import get_company_profile

        with patch(self._PATCH_TARGET, return_value=_error_response(429)):
            with pytest.raises(RateLimitError):
                get_company_profile("AAPL")

    def test_timeout_propagates_from_get_company_news(self):
        from tradingagents.dataflows.finnhub_common import ThirdPartyTimeoutError
        from tradingagents.dataflows.finnhub_news import get_company_news

        with patch(
            self._PATCH_TARGET,
            side_effect=requests.exceptions.Timeout("timeout"),
        ):
            with pytest.raises(ThirdPartyTimeoutError):
                get_company_news("AAPL", "2024-01-01", "2024-01-10")

    def test_timeout_propagates_from_get_basic_financials(self):
        from tradingagents.dataflows.finnhub_common import ThirdPartyTimeoutError
        from tradingagents.dataflows.finnhub_fundamentals import get_basic_financials

        with patch(
            self._PATCH_TARGET,
            side_effect=requests.exceptions.Timeout("timeout"),
        ):
            with pytest.raises(ThirdPartyTimeoutError):
                get_basic_financials("AAPL")
