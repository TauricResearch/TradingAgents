"""Snapshot fundamentals must not leak the present into a backtest.

Statement endpoints were already date-filtered, but the vendor "overview"
endpoints (yfinance ``.info``, Alpha Vantage OVERVIEW) return a live quote:
market cap, TTM ratios, the 52-week range and the 50/200-day averages always
describe today. Replaying 2024-11-01 therefore fed the fundamentals analyst a
200-day average from the present, contradicting the ``close_200_sma`` the market
analyst computed as of the trade date and derailing the debate.
"""
import json

import pandas as pd
import pytest

import tradingagents.dataflows.alpha_vantage_fundamentals as avf
import tradingagents.dataflows.y_finance as yfin
from tradingagents.dataflows.stockstats_utils import is_historical_date

LEAKY_LABELS = ("Market Cap", "52 Week High", "50 Day Average", "200 Day Average")

_INFO = {
    "longName": "Bitcoin USD",
    "sector": "Crypto",
    "marketCap": 1315814113280,
    "fiftyTwoWeekHigh": 126198.07,
    "fiftyDayAverage": 63092.676,
    "twoHundredDayAverage": 72809.93,
}

_OVERVIEW = json.dumps({
    "Symbol": "AAPL",
    "Name": "Apple Inc",
    "Sector": "TECHNOLOGY",
    "Description": "Apple completed its 2025 acquisition of ExampleCorp.",
    "MarketCapitalization": "3000000000000",
    "PERatio": "35.2",
    "52WeekHigh": "260.1",
    "200DayMovingAverage": "220.5",
})


@pytest.fixture
def fake_info(monkeypatch):
    class _FakeTicker:
        def __init__(self, symbol):
            self.info = dict(_INFO)

    monkeypatch.setattr(yfin.yf, "Ticker", _FakeTicker)


@pytest.mark.unit
@pytest.mark.parametrize("curr_date,expected", [
    ("2024-11-01", True),
    (None, False),
    ("", False),
    ("2999-01-01", False),
    ("not-a-date", False),
])
def test_is_historical_date(curr_date, expected):
    assert is_historical_date(curr_date) is expected


@pytest.mark.unit
def test_today_is_not_historical():
    """The boundary the `<` comparison hinges on: today is live, not a replay."""
    today = pd.Timestamp.today().normalize()

    assert is_historical_date(today.strftime("%Y-%m-%d")) is False
    assert is_historical_date((today - pd.Timedelta(days=1)).strftime("%Y-%m-%d")) is True


@pytest.mark.unit
def test_yfinance_withholds_snapshot_metrics_on_past_date(fake_info):
    report = yfin.get_fundamentals("BTC-USD", "2024-11-01")

    for label in LEAKY_LABELS:
        assert label not in report
    assert "72809.93" not in report
    assert "Bitcoin USD" in report
    assert "look-ahead bias" in report
    assert "2024-11-01" in report


@pytest.mark.unit
def test_yfinance_keeps_snapshot_metrics_without_date(fake_info):
    report = yfin.get_fundamentals("BTC-USD", None)

    for label in LEAKY_LABELS:
        assert label in report
    assert "72809.93" in report


@pytest.mark.unit
def test_yfinance_reports_note_when_no_safe_fields_survive(monkeypatch):
    """Withholding everything is not the same as an unknown symbol."""
    class _PriceOnlyTicker:
        def __init__(self, symbol):
            self.info = {"marketCap": 123, "twoHundredDayAverage": 72809.93}

    monkeypatch.setattr(yfin.yf, "Ticker", _PriceOnlyTicker)

    report = yfin.get_fundamentals("BTC-USD", "2024-11-01")

    assert "72809.93" not in report
    assert "look-ahead bias" in report


@pytest.mark.unit
def test_alpha_vantage_strips_snapshot_keys_on_past_date():
    payload = json.loads(avf._strip_snapshot_fields(_OVERVIEW, "2024-11-01"))

    assert set(payload) == {"Symbol", "Name", "Sector", "Note"}
    assert "look-ahead bias" in payload["Note"]
    # Vendor prose gets rewritten, so it can narrate events after curr_date.
    assert "2025 acquisition" not in avf._strip_snapshot_fields(_OVERVIEW, "2024-11-01")


@pytest.mark.unit
@pytest.mark.parametrize("body,curr_date", [
    (_OVERVIEW, None),
    ("Our standard API rate limit is 25 requests per day", "2024-11-01"),
    (json.dumps(["unexpected", "shape"]), "2024-11-01"),
])
def test_alpha_vantage_passes_through_unchanged(body, curr_date):
    assert avf._strip_snapshot_fields(body, curr_date) == body
