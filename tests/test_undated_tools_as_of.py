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
