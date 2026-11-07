"""Valuation inputs obey the repo's point-in-time rule: only what was public on the run date.

SEC EDGAR dates every fact by its filing, so a past run reads the figures as filed then. Yahoo
dates statements by the period they cover and ``Ticker.info`` is present-day only, so a past run
is told they are withheld without a request being made.
"""

from datetime import date, timedelta
from unittest import mock

import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors import sec_edgar
from tradingagents.dataflows.vendors.yahoo import valuation as yahoo_valuation

PAST = "2024-03-14"


def _fy(end: str, val: float, filed: str, form: str = "10-K") -> dict:
    start = (date.fromisoformat(end) - timedelta(days=364)).isoformat()
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def _instant(end: str, val: float, filed: str, form: str = "10-Q") -> dict:
    return {"end": end, "val": val, "filed": filed, "form": form}


def _facts() -> dict:
    return {"facts": {
        "us-gaap": {
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
                _fy("2022-12-31", 100e6, "2023-02-01"),
                _fy("2023-12-31", 110e6, "2024-02-02"),
                _fy("2024-12-31", 999e6, "2025-02-03"),          # filed after the run date
                _fy("2022-12-31", 95e6, "2024-06-01"),           # a restatement filed after the run date
            ]}},
            "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [
                _fy("2022-12-31", 30e6, "2023-02-01"), _fy("2023-12-31", 35e6, "2024-02-02"),
            ]}},
            "LongTermDebtNoncurrent": {"units": {"USD": [
                _instant("2023-12-31", 400e6, "2024-02-02", "10-K"),
                _instant("2024-06-30", 900e6, "2024-08-01"),     # a later 10-Q
            ]}},
            "DebtCurrent": {"units": {"USD": [_instant("2023-12-31", 50e6, "2024-02-02", "10-K")]}},
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                _instant("2023-12-31", 80e6, "2024-02-02", "10-K")]}},
            "InterestExpense": {"units": {"USD": [_fy("2023-12-31", 27e6, "2024-02-02")]}},
        },
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": "2024-01-15", "val": 1000, "filed": "2024-02-02", "form": "10-K"},
            {"end": "2025-01-15", "val": 2000, "filed": "2025-02-03", "form": "10-K"},
        ]}}},
    }}


@pytest.fixture
def edgar():
    with mock.patch.object(sec_edgar, "cik_for", return_value="0000000001"), \
            mock.patch.object(sec_edgar, "_cached_json", return_value=_facts()):
        yield


@pytest.mark.unit
def test_edgar_inputs_ignore_facts_filed_after_the_run_date(edgar):
    data = sec_edgar.get_valuation_inputs("ACME", PAST)

    assert [p["end"] for p in data["periods"]] == ["2022-12-31", "2023-12-31"]
    assert data["periods"][-1]["cfo"] == 110e6            # not the FY2024 figure filed in 2025
    assert data["shares"] == 1000                         # not the 2025 cover-page count
    assert data["total_debt"] == 450e6 and data["cash"] == 80e6
    assert data["interest_expense"] == 27e6


@pytest.mark.unit
def test_edgar_inputs_read_a_restated_figure_as_first_reported(edgar):
    data = sec_edgar.get_valuation_inputs("ACME", PAST)
    assert data["periods"][0]["cfo"] == 100e6             # restated to 95M on 2024-06-01

    later = sec_edgar.get_valuation_inputs("ACME", "2024-12-31")
    assert later["periods"][0]["cfo"] == 95e6             # known by then


@pytest.mark.unit
def test_edgar_balance_items_come_from_the_latest_filing_known_by_the_date(edgar):
    assert sec_edgar.get_valuation_inputs("ACME", "2024-09-01")["total_debt"] == 950e6   # the 10-Q
    assert sec_edgar.get_valuation_inputs("ACME", PAST)["total_debt"] == 450e6


@pytest.mark.unit
def test_edgar_leaves_untagged_figures_unavailable_rather_than_zero(edgar):
    data = sec_edgar.get_valuation_inputs("ACME", PAST)
    assert data["income_tax"] is None and data["pretax_income"] is None and data["equity"] is None


@pytest.mark.unit
def test_edgar_says_so_when_nothing_was_filed_yet(edgar):
    with pytest.raises(NoMarketDataError, match="no annual operating cash flow"):
        sec_edgar.get_valuation_inputs("ACME", "2021-01-01")


@pytest.mark.unit
def test_edgar_refuses_a_ticker_that_is_not_a_us_filer():
    with mock.patch.object(sec_edgar, "cik_for", return_value=None), \
            pytest.raises(NoMarketDataError, match="not a US SEC filer"):
        sec_edgar.get_valuation_inputs("2222.SR", PAST)


@pytest.mark.unit
def test_yahoo_withholds_inputs_from_a_past_run_without_asking():
    with mock.patch.object(yahoo_valuation, "yf_retry", side_effect=AssertionError("requested")), \
            pytest.raises(NoMarketDataError, match="withheld"):
        yahoo_valuation.get_valuation_inputs("SAP.DE", PAST)


@pytest.mark.unit
def test_yahoo_withholds_peer_multiples_from_a_past_run_without_asking():
    with mock.patch.object(yahoo_valuation, "yf_retry", side_effect=AssertionError("requested")), \
            pytest.raises(NoMarketDataError, match=f"withheld for {PAST}"):
        yahoo_valuation.get_peer_snapshot("SAP.DE", PAST)


@pytest.mark.unit
def test_price_history_never_asks_for_a_later_day():
    import pandas as pd

    from tradingagents.dataflows.vendors.yahoo import market

    with mock.patch.object(market, "get_closes", return_value=pd.Series(dtype=float)) as asked:
        market.get_final_closes("AAPL", PAST, 30)
    symbol, start, end = asked.call_args.args
    assert end == "2024-03-15"            # exclusive: the run date is the last day read
    assert start == "2024-02-13"
