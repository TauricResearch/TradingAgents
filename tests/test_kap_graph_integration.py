from __future__ import annotations

import json

import pandas as pd
import pytest
from langgraph.prebuilt import ToolNode

from tradingagents.agents.analysts.kap_analyst import create_kap_analyst
from tradingagents.agents.utils.kap_data_tools import get_kap_disclosures
from tradingagents.dataflows.kap.models import KapDisclosureResult
from tradingagents.graph.analyst_execution import build_analyst_execution_plan
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.trading_graph import TradingAgentsGraph, filter_enabled_analysts


def test_kap_agent_state_is_initialized():
    state = Propagator().create_initial_state("THYAO.IS", "2026-08-20")
    assert state["kap_report"] == ""


def test_analyst_plan_places_kap_between_news_and_fundamentals():
    plan = build_analyst_execution_plan(["market", "social", "news", "kap", "fundamentals"])
    assert [spec.key for spec in plan.specs] == [
        "market", "social", "news", "kap", "fundamentals"
    ]
    kap = plan.specs[3]
    assert (kap.agent_node, kap.tool_node, kap.report_key) == (
        "KAP Analyst", "tools_kap", "kap_report"
    )


def test_kap_can_be_disabled_without_affecting_other_analysts():
    selected = ["market", "social", "news", "kap", "fundamentals"]
    assert filter_enabled_analysts(selected, {"kap_enabled": False}) == (
        "market", "social", "news", "fundamentals"
    )


def test_kap_toolnode_exposes_only_kap_tool():
    nodes = TradingAgentsGraph._create_tool_nodes(None)
    assert set(nodes["kap"].tools_by_name) == {"get_kap_disclosures"}


def test_langgraph_connects_kap_node_between_start_and_research(monkeypatch):
    import tradingagents.graph.setup as setup_module

    def no_op_node(state):
        return {}

    for name in dir(setup_module):
        if name.startswith("create_"):
            monkeypatch.setattr(setup_module, name, lambda *args, **kwargs: no_op_node)

    workflow = GraphSetup(
        None,
        None,
        {"kap": ToolNode([get_kap_disclosures])},
        ConditionalLogic(),
    ).setup_graph(["kap"])

    assert ("__start__", "KAP Analyst") in workflow.edges
    assert ("tools_kap", "KAP Analyst") in workflow.edges
    assert ("Msg Clear KAP", "Bull Researcher") in workflow.edges
    assert "KAP Analyst" in workflow.branches


def test_non_bist_kap_analyst_skips_llm_and_returns_controlled_report():
    class NeverCallLLM:
        def bind_tools(self, tools):
            raise AssertionError("LLM must not run for non-BIST symbols")

    node = create_kap_analyst(NeverCallLLM())
    result = node(
        {
            "company_of_interest": "AAPL",
            "trade_date": "2026-08-20",
            "messages": [],
            "asset_type": "stock",
        }
    )
    assert "UYGULANAMAZ" in result["kap_report"]
    assert result["messages"][0].tool_calls == []
    assert ConditionalLogic().should_continue_kap(
        {"messages": result["messages"]}
    ) == "Msg Clear KAP"


def test_kap_tool_failure_is_data_not_exception(monkeypatch):
    failure = KapDisclosureResult(
        status="unavailable",
        ticker="THYAO.IS",
        kap_ticker="THYAO",
        start_date="2026-07-21",
        end_date="2026-08-20",
        message="KAP verisi geçici olarak alınamadı. Analiz diğer verilerle devam edebilir.",
    )

    monkeypatch.setattr(
        "tradingagents.agents.utils.kap_data_tools.KapService.get_disclosures",
        lambda self, **kwargs: failure,
    )
    payload = json.loads(
        get_kap_disclosures.invoke(
            {"ticker": "THYAO.IS", "start_date": "2026-07-21", "end_date": "2026-08-20"}
        )
    )
    assert payload["status"] == "unavailable"
    assert "devam" in payload["message"]


def test_invalid_kap_tool_arguments_do_not_abort_graph():
    payload = json.loads(
        get_kap_disclosures.invoke(
            {"ticker": "THYAO.IS", "start_date": "2026-08-21", "end_date": "2026-08-20"}
        )
    )
    assert payload["status"] == "unavailable"
    assert "parametreleri geçersiz" in payload["message"]


@pytest.mark.parametrize("ticker", ["THYAO.IS", "ASELS.IS", "TUPRS.IS"])
def test_bist_benchmark_is_xu100_and_never_spy(ticker):
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"benchmark_ticker": None, "benchmark_map": {".IS": "^XU100", "": "SPY"}}
    assert graph._resolve_benchmark(ticker) == "^XU100"


def test_unavailable_xu100_data_does_not_crash_return_calculation(monkeypatch):
    class EmptyTicker:
        def history(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr("tradingagents.graph.trading_graph.yf.Ticker", lambda symbol: EmptyTicker())
    graph = object.__new__(TradingAgentsGraph)
    assert graph._fetch_returns(
        "THYAO.IS", "2026-08-20", benchmark="^XU100"
    ) == (None, None, None)
