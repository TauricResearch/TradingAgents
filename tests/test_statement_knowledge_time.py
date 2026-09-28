"""A historical run is served statements only with a known filing time.

SEC EDGAR dates every filing, so it serves a past date as filed. Yahoo and Alpha
Vantage date a statement by the period it covers, which a company publishes weeks
later, so a past run is told they are withheld rather than served figures that may
not yet have been public.
"""

import copy
from unittest import mock

import pytest

from tradingagents import default_config
from tradingagents.dataflows import router
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.vendors.alpha_vantage import fundamentals as alpha_vantage
from tradingagents.dataflows.vendors.yahoo import fundamentals as yahoo

PAST = "2024-03-14"


@pytest.mark.unit
@pytest.mark.parametrize("statement", [yahoo.get_balance_sheet, yahoo.get_cashflow, yahoo.get_income_statement])
def test_yahoo_withholds_statements_from_a_past_run_without_asking(statement):
    with mock.patch.object(yahoo, "yf_retry", side_effect=AssertionError("requested")):
        out = statement("SAP.DE", "quarterly", PAST)
    assert "withheld" in out and PAST in out and "filing date" in out


@pytest.mark.unit
@pytest.mark.parametrize("statement", [alpha_vantage.get_balance_sheet, alpha_vantage.get_cashflow,
                                       alpha_vantage.get_income_statement])
def test_alpha_vantage_withholds_statements_from_a_past_run_without_asking(statement):
    with mock.patch.object(alpha_vantage, "_make_api_request", side_effect=AssertionError("requested")):
        out = statement("IBM", "quarterly", PAST)
    assert "withheld" in out and PAST in out


@pytest.mark.unit
def test_a_current_run_is_still_served_yahoo_statements():
    import pandas as pd

    from tradingagents.dataflows.date_window import get_current_date

    frame = pd.DataFrame({pd.Timestamp("2026-06-30"): [1.0]}, index=["Total Assets"])
    with mock.patch.object(yahoo, "yf_retry", return_value=frame):
        out = yahoo.get_balance_sheet("SAP.DE", "quarterly", get_current_date())
    assert "Total Assets" in out and "withheld" not in out


@pytest.mark.unit
def test_statements_come_from_sec_edgar_first_by_default():
    set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))
    served = []
    chain = {name: (lambda *a, _n=name, **k: served.append(_n) or f"{_n} statements")
             for name in router.VENDOR_METHODS["get_balance_sheet"]}
    with mock.patch.dict(router.VENDOR_METHODS, {"get_balance_sheet": chain}):
        router.route_to_vendor("get_balance_sheet", "AAPL", "quarterly", PAST)
    assert served == ["sec_edgar"]


@pytest.mark.unit
def test_yahoo_withholds_insider_trades_from_a_past_run_without_asking():
    """A trade is dated when it happened; it became public with its Form 4, up to
    two business days later, and Yahoo reports no filing date."""
    with mock.patch.object(yahoo, "yf_retry", side_effect=AssertionError("requested")):
        out = yahoo.get_insider_transactions("AAPL", PAST)
    assert "withheld" in out and PAST in out


@pytest.mark.unit
def test_alpha_vantage_withholds_insider_trades_from_a_past_run_without_asking():
    from tradingagents.dataflows.vendors.alpha_vantage import news as alpha_vantage_news

    with mock.patch.object(alpha_vantage_news, "_make_api_request", side_effect=AssertionError("requested")):
        out = alpha_vantage_news.get_insider_transactions("IBM", PAST)
    assert "withheld" in out and PAST in out
