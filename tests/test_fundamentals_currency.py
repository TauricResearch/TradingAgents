"""Yahoo's money fields say which currency they are in.

``Ticker.info`` gives the market figures (market cap, EPS, price levels) in the
trading currency (``currency``) and the statement figures (revenue, net income)
in the reporting currency (``financialCurrency``). For an ADR the two differ:
PBR trades in USD and reports in BRL, so its market cap over its net income
reads as a P/E of 1 where Yahoo's own is 5.3.
"""

from unittest import mock

import pytest

from tradingagents.dataflows import date_window
from tradingagents.dataflows.vendors.yahoo import fundamentals

TODAY = "2026-09-30"


def _lines(info):
    with mock.patch.object(date_window, "get_current_date", return_value=TODAY), \
         mock.patch.object(fundamentals, "yf_retry", lambda fn: info):
        return fundamentals.get_fundamentals("PBR", TODAY).splitlines()


@pytest.mark.unit
def test_market_figures_carry_the_trading_currency_and_statement_figures_the_reporting_one():
    lines = _lines({"longName": "Petroleo Brasileiro S.A.", "currency": "USD", "financialCurrency": "BRL",
                    "marketCap": 131271745536, "trailingEps": 3.96, "fiftyTwoWeekHigh": 22.4,
                    "totalRevenue": 548493000704, "netIncomeToCommon": 133376000000,
                    "trailingPE": 5.32197, "bookValue": 14.370242})

    assert "Market Cap: 131271745536 USD" in lines
    assert "EPS (TTM): 3.96 USD" in lines
    assert "52 Week High: 22.4 USD" in lines
    assert "Revenue (TTM): 548493000704 BRL" in lines
    assert "Net Income: 133376000000 BRL" in lines
    assert "PE Ratio (TTM): 5.32197" in lines
    assert "Book Value: 14.370242" in lines


@pytest.mark.unit
def test_figures_stay_bare_when_yahoo_names_no_currency():
    lines = _lines({"longName": "Petroleo Brasileiro S.A.", "marketCap": 131271745536,
                    "netIncomeToCommon": 133376000000})

    assert "Market Cap: 131271745536" in lines
    assert "Net Income: 133376000000" in lines
