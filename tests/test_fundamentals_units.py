"""Yahoo's percentage fields must say they are percentages.

``Ticker.info`` reports ``dividendYield`` and ``debtToEquity`` in percent (0.41 is
0.41%, 78.4 is 78.4%, i.e. 0.78x) and the margins and returns in fractions
(0.27 is 27%). ``get_fundamentals`` prints them side by side, so the two
percentages carry their unit and every other value is unchanged. API access is
mocked.
"""
from __future__ import annotations

from unittest import mock

from tradingagents.dataflows import date_window
from tradingagents.dataflows.vendors.yahoo import fundamentals as yahoo_fundamentals

_TODAY = "2026-09-26"
_INFO = {
    "longName": "Apple Inc.",
    "dividendYield": 0.32,
    "profitMargins": 0.27619,
    "returnOnEquity": 1.4875101,
    "debtToEquity": 78.445,
}


def _fundamentals(info):
    with mock.patch.object(date_window, "get_current_date", return_value=_TODAY), \
         mock.patch.object(yahoo_fundamentals, "yf_retry", lambda fn: info), \
         mock.patch.object(yahoo_fundamentals.yf, "Ticker"):
        return yahoo_fundamentals.get_fundamentals("AAPL", _TODAY)


def test_percentage_fields_carry_their_unit():
    out = _fundamentals(_INFO)
    assert "Dividend Yield: 0.32%" in out
    assert "Debt to Equity: 78.445% (0.78x)" in out


def test_fraction_fields_are_unchanged():
    out = _fundamentals(_INFO)
    assert "Profit Margin: 0.27619" in out
    assert "Return on Equity: 1.4875101" in out


def test_missing_percentage_fields_are_omitted():
    out = _fundamentals({"longName": "JPMorgan Chase & Co.", "profitMargins": 0.35})
    assert "Dividend Yield" not in out
    assert "Debt to Equity" not in out
