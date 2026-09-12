"""Look-ahead guard for the fundamental statement tools.

The vendor-side date filter (``filter_financials_by_date`` /
``_filter_reports_by_date``) only runs when it receives the analysis date, but
the three statement tools used to declare ``curr_date`` optional and forward
``None`` when the model omitted it — silently disabling the filter and letting
fiscal periods dated after the analysis date reach a historical run. These
tests pin the contract that keeps the filter reachable.
"""

from __future__ import annotations

import pandas as pd
import pytest
from pydantic import ValidationError

import tradingagents.dataflows.y_finance as yfmod
import tradingagents.agents.utils.fundamental_data_tools as fdtools
from tradingagents.agents.utils.fundamental_data_tools import (
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
)

STATEMENT_TOOLS = (get_balance_sheet, get_cashflow, get_income_statement)


@pytest.mark.unit
@pytest.mark.parametrize("statement_tool", STATEMENT_TOOLS)
def test_statement_tools_require_curr_date(statement_tool):
    schema = statement_tool.args_schema.model_json_schema()
    assert "curr_date" in schema["required"]
    assert "freq" not in schema["required"]  # frequency stays optional


@pytest.mark.unit
def test_omitting_curr_date_is_rejected_not_silently_unfiltered():
    with pytest.raises(ValidationError):
        get_balance_sheet.invoke({"ticker": "AAPL"})


@pytest.mark.unit
def test_statement_tool_forwards_curr_date_to_the_vendor(monkeypatch):
    seen = {}

    def fake_route(method, *args, **kwargs):
        seen[method] = args
        return "ok"

    monkeypatch.setattr(fdtools, "route_to_vendor", fake_route)
    get_balance_sheet.func("AAPL", "2023-06-30", "annual")
    assert seen["get_balance_sheet"] == ("AAPL", "annual", "2023-06-30")


@pytest.mark.unit
def test_yfinance_statements_drop_fiscal_periods_after_curr_date(monkeypatch):
    # yfinance statements carry fiscal-period columns as of *today*; a backtest
    # date must trim the future ones.
    stmt = pd.DataFrame(
        [[10, 20, 30]],
        columns=pd.to_datetime(["2023-03-31", "2024-09-30", "2025-06-30"]),
        index=["Total Assets"],
    )

    class _FakeTicker:
        def __init__(self, *a):
            self.quarterly_balance_sheet = stmt
            self.balance_sheet = stmt

    monkeypatch.setattr(yfmod.yf, "Ticker", _FakeTicker)
    monkeypatch.setattr(yfmod, "yf_retry", lambda fn: fn())

    body = yfmod.get_balance_sheet("AAPL", curr_date="2023-06-30")
    header = body.split("\n\n", 1)[1].splitlines()[0]
    assert header == ",2023-03-31"
