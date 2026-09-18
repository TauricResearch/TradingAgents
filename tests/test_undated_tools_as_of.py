"""Insider filings and prediction-market odds are bounded by the run's trade date.

Neither tool takes a date from the model, so the run's trade_date is injected from
graph state. Insider filings carry dates and are filtered to it; Polymarket serves
only live odds, so a historical run withholds them.
"""

from __future__ import annotations

import json
from unittest import mock

import pandas as pd
import pytest

from tradingagents.agents.utils import news_data_tools, prediction_markets_tools
from tradingagents.dataflows import alpha_vantage_news, polymarket, y_finance


def _insider_frame(*dates):
    return pd.DataFrame({
        "Shares": [100] * len(dates),
        "Text": [f"Sale at price {100 + i} per share." for i in range(len(dates))],
        "Start Date": pd.to_datetime(list(dates)),
    })


def _yf_insider(frame, curr_date):
    ticker = mock.Mock(insider_transactions=frame)
    with mock.patch.object(y_finance.yf, "Ticker", return_value=ticker):
        return y_finance.get_insider_transactions("AAPL", curr_date)


@pytest.mark.unit
def test_yfinance_insider_filings_after_the_date_are_dropped():
    out = _yf_insider(_insider_frame("2026-09-08", "2025-06-02", "2025-05-30", "2025-01-10"), "2025-06-01")
    assert "2026-09-08" not in out and "2025-06-02" not in out
    assert "2025-05-30" in out and "2025-01-10" in out


@pytest.mark.unit
def test_yfinance_insider_date_before_coverage_is_unavailable_not_absent():
    out = _yf_insider(_insider_frame("2026-09-08", "2025-06-02"), "2024-01-01")
    assert "unavailable" in out and "No insider transactions reported" not in out
    assert "2025-06-02" in out  # where coverage starts


@pytest.mark.unit
def test_yfinance_insider_without_a_date_is_unfiltered():
    out = _yf_insider(_insider_frame("2026-09-08", "2025-01-10"), None)
    assert "2026-09-08" in out and "2025-01-10" in out


@pytest.mark.unit
def test_alpha_vantage_insider_filings_after_the_date_are_dropped():
    body = json.dumps({"data": [
        {"transaction_date": "2026-09-08", "executive": "A"},
        {"transaction_date": "2025-05-30", "executive": "B"},
    ]})
    with mock.patch.object(alpha_vantage_news, "_make_api_request", return_value=body):
        out = json.loads(alpha_vantage_news.get_insider_transactions("AAPL", "2025-06-01"))
    assert [t["executive"] for t in out["data"]] == ["B"]


@pytest.mark.unit
def test_polymarket_withholds_live_odds_from_a_historical_run():
    with mock.patch.object(polymarket, "_request", side_effect=AssertionError("must not fetch")):
        out = polymarket.get_prediction_markets("Fed rate cut", curr_date="2025-06-01")
    assert "withheld" in out


@pytest.mark.unit
def test_polymarket_serves_a_current_run():
    with mock.patch.object(polymarket, "_request", return_value={"events": []}) as req:
        polymarket.get_prediction_markets("Fed rate cut", curr_date=polymarket.get_current_date())
    req.assert_called_once()


@pytest.mark.unit
@pytest.mark.parametrize("tool", [news_data_tools.get_insider_transactions,
                                  prediction_markets_tools.get_prediction_markets], ids=lambda t: t.name)
def test_trade_date_is_injected_not_model_visible(tool):
    assert "trade_date" in tool.func.__code__.co_varnames
    props = tool.tool_call_schema.model_json_schema()["properties"]
    assert "trade_date" not in props and "curr_date" not in props


# --- the instrument's identity -------------------------------------------------

@pytest.mark.unit
def test_a_historical_run_is_told_the_identity_is_current(monkeypatch):
    """The company name, sector and industry come from today's vendor profile.
    They are usually right for a past date, but a company that renamed or was
    reclassified since would read wrong, and every agent is told to anchor to
    this identity, so the run has to know which date it describes."""
    from tradingagents.agents.utils.agent_utils import build_instrument_context

    identity = {"company_name": "Example Corp", "sector": "Technology",
                "industry": "Software", "exchange": "NMS"}

    historical = build_instrument_context("EXMP", "stock", identity, curr_date="2024-03-14")
    assert "Example Corp" in historical
    assert "2024-03-14" in historical and "today" in historical.lower()


@pytest.mark.unit
def test_a_current_run_is_not_cluttered_with_a_vintage_note(monkeypatch):
    from tradingagents.agents.utils.agent_utils import build_instrument_context
    from tradingagents.dataflows.utils import get_current_date

    today = build_instrument_context("EXMP", "stock", {"company_name": "Example Corp"},
                                     curr_date=get_current_date())
    assert "Example Corp" in today
    assert "resolved today" not in today.lower()


@pytest.mark.unit
def test_insider_rows_are_dated_by_the_trade_not_the_filing():
    """yfinance reports the transaction date and carries no filing date. A trade
    becomes public when the Form 4 is filed, up to two business days later, so a
    run must not be told these rows were public on their transaction date."""
    import pandas as pd

    from tradingagents.dataflows import y_finance

    frame = pd.DataFrame({
        "Shares": [100, 200],
        "Text": ["Sale at price 10.00 per share.", "Sale at price 11.00 per share."],
        "Start Date": pd.to_datetime(["2026-05-01", "2026-05-20"]),
    })
    ticker = mock.Mock(insider_transactions=frame)
    with mock.patch.object(y_finance.yf, "Ticker", return_value=ticker):
        out = y_finance.get_insider_transactions("AAPL", "2026-05-10")

    assert "2026-05-01" in out and "2026-05-20" not in out   # still bounded by the date
    assert "transaction date" in out.lower()                  # and says what the date means
    assert "filed" in out.lower()                             # and that filing comes later


@pytest.mark.unit
def test_an_indicator_that_could_not_be_read_is_not_shown_as_a_blank_value():
    """The per-day fallback returned an empty string for a failed read, so the
    table rendered a row per day with nothing after the colon: an analyst reads
    that as "no value on that day" rather than "could not be obtained"."""
    from tradingagents.dataflows import y_finance
    from tradingagents.dataflows.errors import VendorError

    with mock.patch.object(y_finance.StockstatsUtils, "get_stock_stats",
                           side_effect=RuntimeError("cache parse failed")), \
            pytest.raises(VendorError):
        y_finance.get_stockstats_indicator("AAPL", "rsi", "2026-05-08")


@pytest.mark.unit
@pytest.mark.parametrize("func, args", [
    # A past date withholds the live profile before any request, so the
    # fundamentals case is exercised on the date it does fetch.
    ("get_fundamentals", ("AAPL", None)),
    ("get_balance_sheet", ("AAPL", "annual", "2026-09-01")),
    ("get_cashflow", ("AAPL", "annual", "2026-09-01")),
    ("get_income_statement", ("AAPL", "annual", "2026-09-01")),
    ("get_insider_transactions", ("AAPL", "2026-09-01")),
])
def test_a_yfinance_failure_is_a_vendor_error_not_a_report(func, args):
    """Returning the failure as text makes the router count it as an answer, so
    the chain stops and the analyst reads the error message as if it were data.
    yfinance serves the default path, so this is the one that matters most."""
    from tradingagents.dataflows import y_finance
    from tradingagents.dataflows.errors import VendorError

    with mock.patch.object(y_finance.yf, "Ticker", side_effect=RuntimeError("yahoo hiccup")), \
            pytest.raises(VendorError):
        getattr(y_finance, func)(*args)


@pytest.mark.unit
@pytest.mark.parametrize("func, args", [
    ("get_news_yfinance", ("AAPL", "2026-08-25", "2026-09-01")),
    ("get_global_news_yfinance", ("2026-09-01", 7, 5)),
])
def test_a_yfinance_news_failure_is_a_vendor_error_not_a_report(func, args):
    from tradingagents.dataflows import yfinance_news
    from tradingagents.dataflows.errors import VendorError

    target = "Ticker" if "global" not in func else "Search"
    with mock.patch.object(yfinance_news.yf, target, side_effect=RuntimeError("yahoo hiccup")), \
            pytest.raises(VendorError):
        getattr(yfinance_news, func)(*args)


@pytest.mark.unit
def test_an_unreachable_vendor_is_not_reported_as_a_missing_symbol(monkeypatch):
    """yfinance returns an empty frame when it cannot reach Yahoo, with no
    exception. Reporting that as "no data for AAPL" tells the analyst the
    company has no balance sheet, when the truth is we could not ask."""
    import pandas as pd

    from tradingagents.dataflows import stockstats_utils, y_finance
    from tradingagents.dataflows.errors import NoMarketDataError, VendorRateLimitError

    empty = mock.Mock(quarterly_balance_sheet=pd.DataFrame(), balance_sheet=pd.DataFrame())
    monkeypatch.setattr(y_finance.yf, "Ticker", lambda s: empty)

    monkeypatch.setattr(stockstats_utils, "vendor_reachable", lambda url: False)
    with pytest.raises(VendorRateLimitError, match="unreachable"):
        y_finance.get_balance_sheet("AAPL", "annual", "2026-09-01")

    monkeypatch.setattr(stockstats_utils, "vendor_reachable", lambda url: True)
    with pytest.raises(NoMarketDataError):
        y_finance.get_balance_sheet("AAPL", "annual", "2026-09-01")


@pytest.mark.unit
def test_every_vendor_unavailable_says_so_rather_than_crashing(monkeypatch):
    """A throttled or unreachable chain used to raise RuntimeError('No available
    vendor'), which ends the run, and never said the vendor was the problem."""
    from tradingagents.dataflows import interface
    from tradingagents.dataflows.errors import VendorRateLimitError

    def _down(*a, **k):
        raise VendorRateLimitError("Yahoo Finance is unreachable")

    monkeypatch.setitem(interface.VENDOR_METHODS["get_balance_sheet"], "yfinance", _down)

    out = interface.route_to_vendor("get_balance_sheet", "AAPL", "annual", "2026-09-01")

    assert "unavailable" in out.lower() and "unreachable" in out.lower()
    assert "delisted" not in out.lower()  # not a claim about the symbol


@pytest.mark.unit
def test_the_price_path_also_tells_an_outage_from_an_unknown_symbol(monkeypatch):
    """Prices are the most-used path, so an outage there must not read as a
    delisted symbol either."""
    import pandas as pd

    from tradingagents.dataflows import stockstats_utils, y_finance
    from tradingagents.dataflows.errors import NoMarketDataError, VendorRateLimitError

    monkeypatch.setattr(y_finance.yf, "Ticker", lambda s: mock.Mock(history=lambda **k: pd.DataFrame()))

    monkeypatch.setattr(stockstats_utils, "vendor_reachable", lambda url: False)
    with pytest.raises(VendorRateLimitError, match="unreachable"):
        y_finance.get_YFin_data_online("AAPL", "2026-09-01", "2026-09-10")

    monkeypatch.setattr(stockstats_utils, "vendor_reachable", lambda url: True)
    with pytest.raises(NoMarketDataError):
        y_finance.get_YFin_data_online("AAPL", "2026-09-01", "2026-09-10")
