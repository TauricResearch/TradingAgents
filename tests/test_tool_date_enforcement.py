"""Dated tools take the analysis date from graph state, not from the model.

Every point-in-time guard behind a tool trusts the date it is given. A model that
omits the date, or passes today's instead of the analysis date, would otherwise
walk past them. The run's trade_date is injected from state and hidden from the
model-visible schema.
"""

from __future__ import annotations

from unittest import mock

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents.utils import (
    core_stock_tools,
    fundamental_data_tools,
    macro_data_tools,
    market_data_validation_tools,
    news_data_tools,
    technical_indicators_tools,
)
from tradingagents.dataflows.date_window import as_of, as_of_window

TRADE_DATE = "2026-08-14"


@pytest.mark.unit
@pytest.mark.parametrize("requested, expected", [
    ("2026-09-14", TRADE_DATE),     # later than the run: clamped
    ("2026-08-01", "2026-08-01"),   # earlier: narrows, allowed
    (None, TRADE_DATE),             # omitted
    ("Sept 1", TRADE_DATE),         # unparseable
    ("", TRADE_DATE),
])
def test_as_of_takes_the_earlier_date(requested, expected):
    assert as_of(requested, TRADE_DATE) == expected


@pytest.mark.unit
def test_as_of_without_a_trade_date_passes_the_request_through():
    assert as_of("2026-09-14", "") == "2026-09-14"


@pytest.mark.unit
@pytest.mark.parametrize("start, end, expected", [
    ("2026-08-01", "2026-09-14", ("2026-08-01", TRADE_DATE)),  # end clamped
    ("2026-08-01", "2026-08-10", ("2026-08-01", "2026-08-10")),  # inside: unchanged
    ("2026-09-01", "2026-09-08", ("2026-08-07", TRADE_DATE)),  # wholly later: span kept, moved back
])
def test_as_of_window(start, end, expected):
    assert as_of_window(start, end, TRADE_DATE) == expected


DATED_TOOLS = [
    core_stock_tools.get_stock_data,
    fundamental_data_tools.get_fundamentals,
    fundamental_data_tools.get_balance_sheet,
    fundamental_data_tools.get_cashflow,
    fundamental_data_tools.get_income_statement,
    news_data_tools.get_news,
    news_data_tools.get_global_news,
    technical_indicators_tools.get_indicators,
    macro_data_tools.get_macro_indicators,
    market_data_validation_tools.get_verified_market_snapshot,
]


@pytest.mark.unit
@pytest.mark.parametrize("tool", DATED_TOOLS, ids=lambda t: t.name)
def test_trade_date_is_hidden_from_the_model(tool):
    assert "trade_date" not in tool.tool_call_schema.model_json_schema()["properties"]


class _State(MessagesState):
    trade_date: str


def _run(tool, args, module):
    """Call the tool through a ToolNode in a graph carrying the run's trade_date."""
    graph = StateGraph(_State)
    graph.add_node("tools", ToolNode([tool]))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    with mock.patch.object(module, "route_to_vendor", return_value="ok") as routed:
        graph.compile().invoke({
            "messages": [AIMessage("", tool_calls=[{"name": tool.name, "args": args, "id": "1"}])],
            "trade_date": TRADE_DATE,
        })
    return routed.call_args.args


@pytest.mark.unit
def test_statement_tool_with_omitted_date_uses_the_run_date():
    args = _run(fundamental_data_tools.get_balance_sheet, {"ticker": "AAPL"}, fundamental_data_tools)
    assert args[-1] == TRADE_DATE  # #1331: an omitted date no longer means unfiltered


@pytest.mark.unit
def test_future_curr_date_from_the_model_is_clamped():
    args = _run(fundamental_data_tools.get_fundamentals,
                {"ticker": "AAPL", "curr_date": "2026-09-14"}, fundamental_data_tools)
    assert args == ("get_fundamentals", "AAPL", TRADE_DATE)


@pytest.mark.unit
def test_future_window_from_the_model_is_clamped():
    args = _run(core_stock_tools.get_stock_data,
                {"symbol": "AAPL", "start_date": "2026-08-01", "end_date": "2026-09-14"}, core_stock_tools)
    assert args == ("get_stock_data", "AAPL", "2026-08-01", TRADE_DATE)


@pytest.mark.unit
def test_direct_call_without_state_is_unchanged():
    with mock.patch.object(news_data_tools, "route_to_vendor", return_value="ok") as routed:
        news_data_tools.get_news.func("AAPL", "2026-09-01", "2026-09-08")
    assert routed.call_args.args == ("get_news", "AAPL", "2026-09-01", "2026-09-08")


# --- the run date itself (#1319) -------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("bad", ["2026-9-10", "2026-09-10 00:00", "Sept 10", None])
def test_propagate_rejects_a_non_canonical_date(bad):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        object.__new__(TradingAgentsGraph).propagate("AAPL", bad)


@pytest.mark.unit
def test_propagate_rejects_a_future_date(monkeypatch):
    import tradingagents.graph.trading_graph as tg

    monkeypatch.setattr(tg, "get_current_date", lambda: "2026-09-10")
    with pytest.raises(ValueError, match="future"):
        object.__new__(tg.TradingAgentsGraph).propagate("AAPL", "2026-09-11")
