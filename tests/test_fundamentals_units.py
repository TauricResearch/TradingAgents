"""Yahoo's percent-valued fields say they are percentages (#1414).

``Ticker.info`` gives ``dividendYield`` and ``debtToEquity`` in percent (0.41 is
0.41%; 78.4 is 78.4%, a ratio of 0.78) but margins and returns as fractions
(0.27 is 27%). Printed side by side without a unit, one scale reads as the other.
"""

from unittest import mock

import pytest

from tradingagents.dataflows import date_window
from tradingagents.dataflows.vendors.yahoo import fundamentals

TODAY = "2026-09-26"


def _fundamentals(info):
    with mock.patch.object(date_window, "get_current_date", return_value=TODAY), \
         mock.patch.object(fundamentals, "yf_retry", lambda fn: info):
        return fundamentals.get_fundamentals("AAPL", TODAY)


@pytest.mark.unit
def test_percent_fields_carry_their_unit_and_fractions_are_unchanged():
    out = _fundamentals({"longName": "Apple Inc.", "dividendYield": 0.32, "debtToEquity": 78.445,
                         "profitMargins": 0.27619, "returnOnEquity": 1.4875101})

    assert "Dividend Yield: 0.32%" in out
    assert "Debt to Equity: 78.445% (0.78x)" in out
    assert "Profit Margin: 0.27619" in out
    assert "Return on Equity: 1.4875101" in out


@pytest.mark.unit
def test_an_absent_percent_field_is_left_out():
    out = _fundamentals({"longName": "JPMorgan Chase & Co.", "profitMargins": 0.35})

    assert "Dividend Yield" not in out and "Debt to Equity" not in out
