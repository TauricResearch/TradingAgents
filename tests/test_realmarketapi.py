"""RealMarketAPI vendor: symbol mapping, hourly history paging and the daily
resample, the recent D1 window and how its bars are dated, error-code mapping, indicators, and router integration.

All HTTP is mocked, so these run without a network connection or a key.
"""
import json
from datetime import datetime, timedelta

import pytest
import requests

from tradingagents.dataflows import router
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.vendors import realmarketapi as rma

KEY = "test-key-not-real"


def _response(body, status=200):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    response.headers["Content-Type"] = (
        "application/problem+json" if status >= 400 else "application/json"
    )
    return response


def _problem(code, status=400):
    return _response({"status": status, "errors": [{"errorCode": code, "message": "nope"}]}, status)


def _candle(open_time, o, h, low, c, v=1.0):
    return {
        "symbolCode": "XAUUSD", "openPrice": o, "highPrice": h, "lowPrice": low,
        "closePrice": c, "volume": v, "openTime": open_time,
    }


class FakeAPI:
    """Serves /candle and paged /history from canned rows, recording each call."""

    def __init__(self, daily=(), hours=(), page_size=2, history_pages=None):
        self.daily = list(daily)
        # The API sends history newest first.
        self.hours = sorted(hours, key=lambda r: r["openTime"], reverse=True)
        self.page_size = page_size
        self.history_pages = history_pages
        self.calls = []

    def __call__(self, url, *, params, timeout, secret, passthrough=()):
        self.calls.append((url.rsplit("/", 1)[-1], dict(params)))
        assert params["apiKey"] == KEY and secret == KEY
        if url.endswith("/candle"):
            return _response({"data": self.daily, "totalCount": len(self.daily)})
        page = params["pageNumber"]
        chunk = self.hours[(page - 1) * self.page_size: page * self.page_size]
        total = self.history_pages or -(-len(self.hours) // self.page_size)
        return _response({
            "data": chunk, "totalCount": len(self.hours), "currentPage": page,
            "totalPages": total, "pageSize": self.page_size,
        })

    def endpoints(self):
        return [name for name, _ in self.calls]


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("REALMARKETAPI_API_KEY", KEY)


@pytest.fixture
def api(monkeypatch):
    def install(fake):
        monkeypatch.setattr(rma, "get_scrubbed", fake)
        return fake
    return install


def _recent_days(n, end=None):
    """n consecutive D1 candles ending at ``end`` (default today), closes 100..100+n-1."""
    end = end or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days = [end - timedelta(days=n - 1 - i) for i in range(n)]
    return [
        _candle(d.strftime("%Y-%m-%dT00:00:00+00:00"), 100 + i, 101 + i, 99 + i, 100 + i)
        for i, d in enumerate(days)
    ]


@pytest.mark.unit
class TestSymbolsAndKey:
    def test_symbols_map_to_broker_names(self):
        assert rma.to_api_symbol("xauusd+") == "XAUUSD"
        assert rma.to_api_symbol("EURUSD=X") == "EURUSD"
        assert rma.to_api_symbol("BTC-USD") == "BTCUSD"
        assert rma.to_api_symbol("GBP/JPY") == "GBPJPY"

    def test_missing_key_is_not_configured(self, monkeypatch):
        monkeypatch.delenv("REALMARKETAPI_API_KEY")
        with pytest.raises(rma.RealMarketAPINotConfiguredError) as err:
            rma.get_stock("XAUUSD", "2025-01-01", "2025-01-10")
        assert isinstance(err.value, VendorNotConfiguredError)


@pytest.mark.unit
class TestHistory:
    HOURS = [
        # 2025-03-03 in UTC, sent with different offsets.
        _candle("2025-03-03T00:00:00+00:00", 10, 12, 9, 11, 1),
        _candle("2025-03-03T10:00:00+09:00", 11, 15, 10, 14, 2),   # 01:00 UTC
        _candle("2025-03-03T23:00:00+00:00", 14, 14, 5, 6, 3),
        # 2025-03-04; the first hour is sent as 2025-03-03 19:00 in New York.
        _candle("2025-03-03T19:00:00-05:00", 20, 21, 19, 20, 4),
        _candle("2025-03-04T12:00:00+00:00", 20, 30, 18, 25, 5),
    ]

    def test_pages_are_fetched_and_resampled_to_daily(self, api):
        # The D1 window starts after the requested range, so history serves it.
        fake = api(FakeAPI(daily=_recent_days(5), hours=self.HOURS, page_size=2))
        out = rma.get_stock("XAUUSD", "2025-03-03", "2025-03-04")

        history = [p for name, p in fake.calls if name == "history"]
        assert [p["pageNumber"] for p in history] == [1, 2, 3]
        assert history[0]["symbolCode"] == "XAUUSD"
        assert history[0]["startTime"] == "2025-03-03T00:00:00Z"
        assert history[0]["endTime"] == "2025-03-05T00:00:00Z"
        assert history[0]["pageSize"] == rma.HISTORY_PAGE_SIZE

        assert out.startswith("# Stock data for XAUUSD from 2025-03-03 to 2025-03-04\n")
        assert "# Total records: 2\n" in out
        # open = first, high = max, low = min, close = last, volume = sum,
        # whatever order the pages arrived in.
        assert "2025-03-03,10.00,15.00,5.00,6.00,6" in out
        assert "2025-03-04,20.00,30.00,18.00,25.00,9" in out

    def test_page_cap_keeps_the_newest_days_and_says_so(self, api, monkeypatch):
        monkeypatch.setattr(rma, "MAX_HISTORY_PAGES", 2)
        fake = api(FakeAPI(daily=[], hours=self.HOURS, page_size=2, history_pages=50))
        out = rma.get_stock("XAUUSD", "2025-01-01", "2025-03-04")

        assert fake.endpoints().count("history") == 2
        # Newest-first hourly pages reach 2025-03-03 only partly, so that day is dropped.
        assert "2025-03-03" not in out.split("\n\n", 1)[1]
        assert "2025-03-04,20.00,30.00,18.00,25.00,9" in out
        assert "# Note: the range exceeds 2 pages of hourly history" in out

    def test_default_cap_reaches_back_about_a_year_of_hourly_bars(self):
        # 1000 hourly rows a page; round-the-clock trading is 24 rows a day.
        days = rma.MAX_HISTORY_PAGES * rma.HISTORY_PAGE_SIZE / 24
        assert 365 <= days <= 2 * 365


@pytest.mark.unit
class TestRecentWindow:
    def test_covered_range_uses_one_candle_request_and_no_later_bar(self, api):
        days = _recent_days(30)
        fake = api(FakeAPI(daily=days))
        start = days[5]["openTime"][:10]
        end = days[20]["openTime"][:10]

        out = rma.get_stock("XAUUSD", start, end)

        assert fake.endpoints() == ["candle"]
        assert fake.calls[0][1]["timeFrame"] == "D1"
        assert "# Total records: 16\n" in out
        assert days[21]["openTime"][:10] not in out

    @pytest.mark.parametrize(
        "open_time",
        [
            "2025-03-03T00:00:00+00:00",   # UTC midnight
            "2025-03-02T22:00:00+00:00",   # UTC+2 server midnight
            "2025-03-02T21:00:00+00:00",   # UTC+3 server midnight
            "2025-03-03T00:00:00+02:00",   # the same open, sent with its offset
        ],
    )
    def test_d1_bar_is_dated_by_the_day_it_covers(self, api, open_time):
        days = _recent_days(3, end=datetime(2025, 3, 1))
        days.append(_candle(open_time, 500, 510, 490, 505))
        api(FakeAPI(daily=days))

        out = rma.get_stock("XAUUSD", "2025-02-27", "2025-03-03")

        assert "2025-03-03,500.00,510.00,490.00,505.00" in out
        assert "2025-03-02," not in out

    def test_stale_rows_are_no_data(self, api):
        api(FakeAPI(daily=_recent_days(30, end=datetime(2025, 1, 31))))
        with pytest.raises(NoMarketDataError, match="stale"):
            rma.get_stock("XAUUSD", "2025-01-10", "2025-03-01")


@pytest.mark.unit
class TestErrors:
    @pytest.mark.parametrize(
        ("response", "error"),
        [
            (_problem("ERR_0005_INVALID_API_KEY", 401), rma.RealMarketAPINotConfiguredError),
            (_problem("ERR_0008_SYMBOL_NOT_SUPPORTED"), NoMarketDataError),
            (_problem("ERR_0001_DATA_NOT_FOUND", 404), NoMarketDataError),
            (_problem("ERR_0017_REQUEST_QUOTA_EXCEEDED", 429), rma.RealMarketAPIRateLimitError),
            (_problem("ERR_0016_INVALID_RANGE_HISTORY"), VendorUnavailableError),
            (_response({"title": "Too Many Requests"}, 429), rma.RealMarketAPIRateLimitError),
        ],
    )
    def test_error_codes_map_to_vendor_errors(self, monkeypatch, response, error):
        monkeypatch.setattr(rma, "get_scrubbed", lambda *a, **k: response)
        with pytest.raises(error):
            rma.get_stock("XAUUSD", "2025-03-03", "2025-03-04")

    def test_network_failure_is_unavailable(self, monkeypatch):
        def fail(*args, **kwargs):
            raise requests.ConnectionError("connection refused")

        monkeypatch.setattr(rma, "get_scrubbed", fail)
        with pytest.raises(VendorUnavailableError, match="connection refused"):
            rma.get_stock("XAUUSD", "2025-03-03", "2025-03-04")

    def test_key_is_not_echoed_in_errors(self, monkeypatch):
        response = _response({"errors": [{"errorCode": "X", "message": f"bad {KEY}"}]}, 400)
        monkeypatch.setattr(rma, "get_scrubbed", lambda *a, **k: response)
        with pytest.raises(VendorUnavailableError) as err:
            rma.get_stock("XAUUSD", "2025-03-03", "2025-03-04")
        assert KEY not in str(err.value)


@pytest.mark.unit
class TestIndicators:
    def test_indicator_is_computed_without_later_bars(self, api):
        days = _recent_days(40)
        api(FakeAPI(daily=days))
        as_of = days[29]["openTime"][:10]

        out = rma.get_indicator("XAUUSD", "close_10_ema", as_of, 5)

        assert out.startswith("## close_10_ema values from ")
        lines = [ln for ln in out.splitlines() if ln[:4].isdigit()]
        assert len(lines) == 6 and lines[0].startswith(f"{as_of}: ")
        # Closes rise by 1 a day; with no later bar, the EMA trails the as-of close.
        assert float(lines[0].split(": ")[1]) < 100 + 29
        assert days[30]["openTime"][:10] not in out

    def test_unknown_indicator_is_rejected(self, api):
        api(FakeAPI(daily=_recent_days(5)))
        with pytest.raises(ValueError, match="not supported"):
            rma.get_indicator("XAUUSD", "nope", "2025-03-03", 5)

    def test_as_of_before_the_window_is_no_data(self, api):
        api(FakeAPI(daily=_recent_days(5)))
        with pytest.raises(NoMarketDataError, match="does not reach back"):
            rma.get_indicator("XAUUSD", "rsi", "2020-01-01", 5)


@pytest.mark.unit
class TestRouting:
    def test_vendor_is_registered_and_opt_in(self):
        assert router.VENDOR_METHODS["get_stock_data"]["realmarketapi"] is rma.get_stock
        assert router.VENDOR_METHODS["get_indicators"]["realmarketapi"] is rma.get_indicator
        assert router.get_vendor("core_stock_apis", "get_stock_data") == "yfinance"

    def test_unsupported_symbol_reaches_the_agent_as_no_data(self, monkeypatch):
        set_config({"data_vendors": {"core_stock_apis": "realmarketapi"}})
        monkeypatch.setattr(
            rma, "get_scrubbed", lambda *a, **k: _problem("ERR_0008_SYMBOL_NOT_SUPPORTED")
        )
        out = router.route_to_vendor("get_stock_data", "AAPL", "2025-03-03", "2025-03-04")
        assert out.startswith("NO_DATA_AVAILABLE")
