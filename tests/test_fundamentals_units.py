"""Yahoo's percent-valued fields say they are percentages (#1414).

``Ticker.info`` gives ``dividendYield`` and ``debtToEquity`` in percent (0.41 is
0.41%; 78.4 is 78.4%, a ratio of 0.78) but margins and returns as fractions
(0.27 is 27%). Printed side by side without a unit, one scale reads as the other.
"""

from unittest import mock

import pandas as pd
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


@pytest.mark.unit
def test_each_money_figure_carries_the_currency_it_is_in():
    """Yahoo quotes London in pence but states EPS and market cap in pounds, and
    the income figures in the reporting currency (#1456)."""
    out = _fundamentals({"longName": "Shell plc", "currency": "GBp", "financialCurrency": "USD",
                         "marketCap": 203440193536, "trailingEps": 3.42, "bookValue": 29.1,
                         "fiftyTwoWeekHigh": 3800.0, "fiftyDayAverage": 3500.5,
                         "totalRevenue": 296600993792, "netIncomeToCommon": 25970999296})

    assert "Market Cap: 203440193536 GBP" in out
    assert "EPS (TTM): 3.42 GBP" in out and "Book Value: 29.1 GBP" in out
    assert "52 Week High: 3800.0 GBp" in out and "50 Day Average: 3500.5 GBp" in out
    assert "Revenue (TTM): 296600993792 USD" in out and "Net Income: 25970999296 USD" in out


@pytest.mark.unit
def test_an_adr_quotes_in_dollars_and_reports_in_its_home_currency():
    out = _fundamentals({"longName": "TSMC", "currency": "USD", "financialCurrency": "TWD",
                         "marketCap": 2365000000000, "trailingEps": 13.21, "totalRevenue": 4440492343296})

    assert "Market Cap: 2365000000000 USD" in out and "EPS (TTM): 13.21 USD" in out
    assert "Revenue (TTM): 4440492343296 TWD" in out


@pytest.mark.unit
def test_a_figure_with_no_stated_currency_is_printed_bare():
    out = _fundamentals({"longName": "X", "marketCap": 1000, "totalRevenue": 50})

    assert "Market Cap: 1000\n" in out + "\n" and "Revenue (TTM): 50" in out and "None" not in out


@pytest.mark.unit
def test_income_figures_without_a_stated_reporting_currency_are_printed_bare():
    """The quote currency is not evidence of the reporting currency (an ADR quotes
    in USD and reports in TWD), so an unknown one is not guessed."""
    out = _fundamentals({"longName": "X", "currency": "USD", "marketCap": 1000, "totalRevenue": 50})

    assert "Market Cap: 1000 USD" in out and "Revenue (TTM): 50\n" in out + "\n"


# --- Free cash flow (#1693) -------------------------------------------------
# Yahoo's ``info["freeCashflow"]`` is *levered* free cash flow, not standard
# FCF (operating cash flow minus capital expenditure). The overview used to
# print it as plain "Free Cash Flow", understating cash generation ~3x on
# NVDA ($41.81B levered vs $127.0B standard, TTM to 2026-11-12).


def _fundamentals_with_statements(info, quarterly=None, annual=None):
    ticker = mock.Mock()
    ticker.info = info
    ticker.quarterly_cashflow = quarterly
    ticker.cashflow = annual
    with mock.patch.object(date_window, "get_current_date", return_value=TODAY), \
         mock.patch.object(fundamentals.yf, "Ticker", return_value=ticker):
        return fundamentals.get_fundamentals("NVDA", TODAY)


def _nvda_quarterly():
    # OCF sums to $134.36B and capex to $7.354B over four quarters, so the
    # standard TTM FCF is $127.006B — the issue's SEC cross-check numbers.
    return pd.DataFrame(
        {
            "2025-12-31": [30.0e9, -1.5e9],
            "2026-03-31": [32.0e9, -1.8e9],
            "2026-06-30": [35.0e9, -2.0e9],
            "2026-09-30": [37.36e9, -2.054e9],
        },
        index=["Operating Cash Flow", "Capital Expenditure"],
    )


@pytest.mark.unit
def test_yahoo_fcf_is_labelled_levered_and_standard_fcf_is_computed():
    out = _fundamentals_with_statements(
        {"longName": "NVIDIA Corporation", "financialCurrency": "USD",
         "freeCashflow": 41810000000},
        quarterly=_nvda_quarterly(),
    )

    assert "Free Cash Flow (TTM): 127006000000.0 USD" in out
    assert "Levered Free Cash Flow (TTM): 41810000000 USD" in out
    assert "\nFree Cash Flow:" not in out  # the old bare label is gone


@pytest.mark.unit
def test_fewer_than_four_quarters_falls_back_to_the_annual_statement():
    quarterly = _nvda_quarterly().iloc[:, -2:]
    annual = pd.DataFrame(
        {"2026-01-31": [100.0, -25.0]},
        index=["Operating Cash Flow", "Capital Expenditure"],
    )
    out = _fundamentals_with_statements(
        {"longName": "NVIDIA Corporation", "financialCurrency": "USD",
         "freeCashflow": 41810000000},
        quarterly=quarterly, annual=annual,
    )

    assert "Free Cash Flow (FY): 75.0 USD" in out
    assert "\nFree Cash Flow (TTM):" not in out


@pytest.mark.unit
def test_a_failed_cashflow_fetch_leaves_the_overview_intact():
    info = {"longName": "NVIDIA Corporation", "financialCurrency": "USD",
            "freeCashflow": 41810000000}
    with mock.patch.object(date_window, "get_current_date", return_value=TODAY), \
         mock.patch.object(fundamentals, "yf_retry",
                           side_effect=[info, RuntimeError("boom"), RuntimeError("boom")]):
        out = fundamentals.get_fundamentals("NVDA", TODAY)

    assert "Levered Free Cash Flow (TTM): 41810000000 USD" in out
    assert "\nFree Cash Flow (TTM):" not in out and "Free Cash Flow (FY)" not in out


@pytest.mark.unit
def test_a_nan_in_the_statement_refuses_the_figure():
    quarterly = _nvda_quarterly()
    quarterly.iloc[0, 0] = float("nan")
    out = _fundamentals_with_statements(
        {"longName": "NVIDIA Corporation", "financialCurrency": "USD",
         "freeCashflow": 41810000000},
        quarterly=quarterly,
    )

    assert "\nFree Cash Flow (TTM):" not in out and "Free Cash Flow (FY)" not in out
    assert "Levered Free Cash Flow (TTM): 41810000000 USD" in out


@pytest.mark.unit
def test_a_statement_missing_a_row_refuses_the_figure():
    quarterly = _nvda_quarterly().drop(index=["Capital Expenditure"])
    out = _fundamentals_with_statements(
        {"longName": "NVIDIA Corporation", "financialCurrency": "USD",
         "freeCashflow": 41810000000},
        quarterly=quarterly,
    )

    assert "\nFree Cash Flow (TTM):" not in out and "Free Cash Flow (FY)" not in out
    assert "Levered Free Cash Flow (TTM): 41810000000 USD" in out
