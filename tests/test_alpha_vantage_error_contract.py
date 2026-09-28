"""Alpha Vantage ``Error Message`` contract handling.

Invalid API calls (unknown symbol, bad function name, malformed params) come
back as ``{"Error Message": "..."}``. Before this fix the raw JSON was
returned as data, which made ``get_stock`` emit a header-only CSV and
``get_indicator`` mislabel the failure as "no data" — the router saw a
"successful" call, never fell back, and analysts received zero-row data.
"""
import pytest

import tradingagents.dataflows.net as net
import tradingagents.dataflows.vendors.alpha_vantage.common as av
import tradingagents.dataflows.vendors.alpha_vantage.indicator as avi
import tradingagents.dataflows.vendors.alpha_vantage.stock as avs
from tests.test_alpha_vantage_hardening import _patched_get

_ERROR_BODY = ('{"Error Message": "Invalid API call. Please retry or visit '
               'the documentation for TIME_SERIES_DAILY."}')


@pytest.mark.unit
def test_error_message_classified_as_vendor_error(monkeypatch):
    monkeypatch.setattr(net.requests, "get", _patched_get(_ERROR_BODY))
    with pytest.raises(av.AlphaVantageApiError):
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "BOGUS"})


@pytest.mark.unit
def test_error_message_is_vendor_error_subclass(monkeypatch):
    # The router catches the base VendorError for its generic failure path;
    # raising a bare Exception would crash the routing loop instead.
    monkeypatch.setattr(net.requests, "get", _patched_get(_ERROR_BODY))
    with pytest.raises(Exception) as exc_info:
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "BOGUS"})
    from tradingagents.dataflows.errors import VendorError
    assert isinstance(exc_info.value, VendorError)


@pytest.mark.unit
def test_get_stock_does_not_return_header_only_csv(monkeypatch):
    # Regression: with the error JSON flowing through as "data",
    # _filter_csv_by_date_range parsed the JSON into a single bogus column,
    # filtered everything out, and returned a one-line CSV that looked like
    # a successful (if empty) response. It must raise instead.
    monkeypatch.setattr(net.requests, "get", _patched_get(_ERROR_BODY))
    with pytest.raises(av.AlphaVantageApiError):
        avs.get_stock("BOGUS", "2026-01-10", "2026-01-20")


@pytest.mark.unit
def test_get_indicator_does_not_mislabel_error_as_no_data(monkeypatch):
    # Regression: the error JSON has a single line, so the len(lines) < 2
    # branch returned "Error: No data returned for rsi" — a success-shaped
    # string hiding an invalid call. It must raise instead.
    monkeypatch.setattr(net.requests, "get", _patched_get(_ERROR_BODY))
    with pytest.raises(av.AlphaVantageApiError):
        avi.get_indicator("BOGUS", "rsi", "2026-01-15", 30)


@pytest.mark.unit
def test_rate_limit_and_key_paths_unchanged(monkeypatch):
    # The new branch must not disturb the #991 classification above it.
    monkeypatch.setattr(net.requests, "get", _patched_get(
        '{"Information": "Our standard API rate limit is 25 requests per day."}'))
    with pytest.raises(av.AlphaVantageRateLimitError):
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    monkeypatch.setattr(net.requests, "get", _patched_get(
        '{"Information": "the parameter apikey is invalid or missing."}'))
    with pytest.raises(av.AlphaVantageNotConfiguredError):
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    monkeypatch.setattr(net.requests, "get", _patched_get(
        '{"Note": "API call frequency is 5 calls per minute."}'))
    with pytest.raises(av.AlphaVantageRateLimitError):
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    # Plain CSV data keeps flowing through untouched.
    monkeypatch.setattr(net.requests, "get", _patched_get(
        "Date,Close\n2025-01-02,1.0"))
    out = av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
    assert out.startswith("Date,Close")
